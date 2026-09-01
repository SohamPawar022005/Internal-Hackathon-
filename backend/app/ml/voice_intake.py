"""
Voice intake — speech-to-text (ASR) and text-to-speech (TTS) with a
pluggable, ordered fallback chain.

────────────────────────────────────────────────────────────────────────
WHY THIS EXISTS
────────────────────────────────────────────────────────────────────────
Sarvam AI works well for Indian-language audio but its automatic
*language detection* is unreliable on short / noisy / code-mixed clips,
and the API itself occasionally times out or rate-limits.  We therefore:

  • run more than one engine and fall back on failure, and
  • never trust an engine's language guess blindly — every transcript is
    passed through ``language.reconcile_language`` which cross-checks the
    guess against the Unicode script and ``langdetect``.

────────────────────────────────────────────────────────────────────────
BACKENDS (all optional, chosen by env var)
────────────────────────────────────────────────────────────────────────
ASR  (env ``ASR_BACKENDS``, default ``"sarvam,groq,whisper"``)
  sarvam   Sarvam AI cloud API.        needs SARVAM_API_KEY
  groq     Groq-hosted Whisper large-v3 needs GROQ_API_KEY. Very fast &
           (OpenAI-compatible endpoint)  cheap, strong multilingual.
  whisper  local faster-whisper.       needs `faster-whisper`, ~1GB model
  google   Google Web Speech API via   needs `SpeechRecognition` (+ffmpeg
           the free `speech_recognition`  for non-WAV input). No key, but
           endpoint.                     rate-limited & English-biased.

TTS  (env ``TTS_BACKENDS``, default ``"sarvam,gtts"``)
  sarvam   Sarvam bulbul TTS.          needs SARVAM_API_KEY, natural voices
  gtts     Google Translate TTS.       needs `gTTS` + network, no key,
                                       robotic but supports all Indic langs

────────────────────────────────────────────────────────────────────────
TWO ASR MODES  (env ``ASR_MODE``, default ``fallback``)
────────────────────────────────────────────────────────────────────────
fallback     Try ``ASR_BACKENDS`` left-to-right; first usable result wins.
             Cheap and fast.  One engine's language guess (reconciled
             against the text) is the answer.

orchestrate  Run every engine in ``ASR_ENSEMBLE`` *in parallel*, then
             cross-check.  Each transcript's language is re-derived from
             its own text (script + langdetect); a weighted vote across
             all engines + scripts + langdetect picks ONE language; the
             transcript that best matches it is returned (Sarvam favoured
             for Indic languages, Whisper/Groq for the rest).  Use this
             when the language keeps coming out wrong — it is the
             "refined output" path.

VERNACULAR NOTE
────────────────────────────────────────────────────────────────────────
Sarvam ASR now calls ``/speech-to-text`` (native-script transcription),
NOT ``/speech-to-text-translate`` (which always returned English — the
reason Marathi/Tamil/etc. "didn't work": every clip came back as English
text tagged ``en``).  All backends also accept an optional
``language_hint`` (bare ISO code the citizen picked); it is forwarded to
each engine and given a vote, but a transcript's own Unicode script can
still override it.

Public API:
  • transcribe_audio(audio_bytes, language_hint=None)          → (transcript, lang) | (None, err)
  • transcribe_audio_detailed(audio_bytes, language_hint=None) → dict (transcript + full breakdown)
  • synthesize_speech(text, language_code)                     → bytes | None
  • list_backends()                                            → dict (introspection / health)
  • SUPPORTED_LANGUAGES                                        → list for the UI picker
"""

from __future__ import annotations

import base64
import io
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Tuple, Union

import requests
from dotenv import load_dotenv

from app.ml.language import (
    INDIC_LANGUAGES,
    bare_code,
    is_indic,
    langdetect_scores,
    reconcile_language,
    script_language,
    to_regional_code,
)

load_dotenv()

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────
SARVAM_API_KEY: Optional[str] = os.getenv("SARVAM_API_KEY") or None
# IMPORTANT: /speech-to-text transcribes in the *original* language.
# The old /speech-to-text-translate endpoint always returned an English
# translation — which is why non-Hindi/English complaints "didn't work":
# Marathi audio came back as English text tagged en.  Override via env
# only if you deliberately want translation.
SARVAM_ASR_URL = os.getenv("SARVAM_ASR_URL", "https://api.sarvam.ai/speech-to-text")
SARVAM_ASR_MODEL = os.getenv("SARVAM_ASR_MODEL", "saarika:v2.5")
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
SARVAM_TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v2")
SARVAM_TTS_SPEAKER = os.getenv("SARVAM_TTS_SPEAKER", "anushka")

GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY") or None
GROQ_ASR_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_ASR_MODEL = os.getenv("GROQ_ASR_MODEL", "whisper-large-v3-turbo")

DEFAULT_ASR_CHAIN = "sarvam,groq,whisper"
DEFAULT_TTS_CHAIN = "sarvam,gtts"

# "fallback"    → try backends in order, first success wins (cheap, fast)
# "orchestrate" → run several backends, cross-check their transcripts and
#                 language guesses, then synthesise one refined result
#                 (slower / more calls, but fixes wrong-language output)
DEFAULT_ASR_MODE = "fallback"
DEFAULT_ASR_ENSEMBLE = "sarvam,groq,whisper"

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")
HTTP_TIMEOUT = int(os.getenv("VOICE_HTTP_TIMEOUT", "30"))


def _chain(env_var: str, default: str) -> list[str]:
    raw = os.getenv(env_var) or default
    return [name.strip().lower() for name in raw.split(",") if name.strip()]


# ════════════════════════════════════════════════════════════════════════
# ASR BACKENDS
# ════════════════════════════════════════════════════════════════════════
# Each backend is a callable(audio_bytes, language_hint) -> (transcript,
# raw_lang, conf).
#   transcript    : str  (non-empty on success)
#   raw_lang      : str | None  — engine's language guess, any format
#   conf          : float | None — engine's confidence in that guess [0,1]
#   language_hint : bare ISO code the citizen selected, or None (auto)
# Backends raise on failure so the chain / ensemble can move on.


def _asr_sarvam(
    audio_bytes: bytes, language_hint: Optional[str] = None,
) -> Tuple[str, Optional[str], Optional[float]]:
    if not SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY not set")
    files = {"file": ("audio.wav", io.BytesIO(audio_bytes), "audio/wav")}
    data = {
        "model": SARVAM_ASR_MODEL,
        "with_timestamps": "false",
        # "unknown" = let Sarvam auto-detect; a hint forces that language.
        "language_code": to_regional_code(language_hint) if language_hint else "unknown",
    }
    headers = {"api-subscription-key": SARVAM_API_KEY}
    resp = requests.post(
        SARVAM_ASR_URL, files=files, data=data, headers=headers,
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    result = resp.json()
    transcript = (result.get("transcript") or "").strip()
    if not transcript:
        raise RuntimeError("Sarvam returned empty transcript")
    conf = result.get("language_probability")
    return (
        transcript,
        result.get("language_code"),
        float(conf) if conf is not None else None,
    )


# Whisper (and Groq's hosted Whisper) return full language *names* in
# verbose output — map the common ones to ISO codes.
_WHISPER_LANG_NAMES = {
    "english": "en", "hindi": "hi", "tamil": "ta", "telugu": "te",
    "kannada": "kn", "malayalam": "ml", "bengali": "bn", "gujarati": "gu",
    "marathi": "mr", "punjabi": "pa", "nepali": "ne", "urdu": "ur",
    "odia": "or", "oriya": "or", "assamese": "as",
}


def _normalize_lang_name(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return _WHISPER_LANG_NAMES.get(value.strip().lower(), value)


def _asr_groq(
    audio_bytes: bytes, language_hint: Optional[str] = None,
) -> Tuple[str, Optional[str], Optional[float]]:
    """Groq's hosted Whisper (OpenAI-compatible endpoint).

    Very fast and cheap; large-v3 / large-v3-turbo quality.  Needs
    GROQ_API_KEY.  `verbose_json` gives us the detected language (as a
    name, which we normalize) but no per-clip confidence score.
    """
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set")
    files = {"file": ("audio.wav", io.BytesIO(audio_bytes), "audio/wav")}
    data = {"model": GROQ_ASR_MODEL, "response_format": "verbose_json"}
    if language_hint:
        data["language"] = language_hint  # ISO-639-1
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    resp = requests.post(
        GROQ_ASR_URL, files=files, data=data, headers=headers,
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    result = resp.json()
    transcript = (result.get("text") or "").strip()
    if not transcript:
        raise RuntimeError("Groq returned empty transcript")
    return transcript, _normalize_lang_name(result.get("language")), None


_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel  # heavy import, keep lazy

        logger.info("Loading faster-whisper model (%s)...", WHISPER_MODEL_SIZE)
        _whisper_model = WhisperModel(
            WHISPER_MODEL_SIZE, device="cpu", compute_type="int8",
        )
        logger.info("faster-whisper model loaded.")
    return _whisper_model


def _asr_whisper(
    audio_bytes: bytes, language_hint: Optional[str] = None,
) -> Tuple[str, Optional[str], Optional[float]]:
    model = _get_whisper_model()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
        tmp.write(audio_bytes)
        tmp.flush()
        segments, info = model.transcribe(
            tmp.name, beam_size=5, language=language_hint or None,
        )
        transcript = " ".join(seg.text.strip() for seg in segments).strip()
    if not transcript:
        raise RuntimeError("Whisper returned empty transcript")
    conf = None
    prob = getattr(info, "language_probability", None)
    if prob is not None:
        conf = float(prob)
    return transcript, getattr(info, "language", None), conf


def _asr_google(
    audio_bytes: bytes, language_hint: Optional[str] = None,
) -> Tuple[str, Optional[str], Optional[float]]:
    """Free Google Web Speech endpoint via the `speech_recognition` lib.

    Notes / caveats:
      • No API key, but undocumented and aggressively rate-limited.
      • Needs 16-bit PCM WAV/AIFF/FLAC input.  We try to feed it the bytes
        directly; if that fails and `pydub` + ffmpeg are available we
        transcode (handles webm/ogg/mp3 from browsers).
      • Google needs to be *told* the language — without a hint it assumes
        US English, so a hint matters far more here than for the others.
    """
    import speech_recognition as sr  # noqa: PLC0415

    recog_lang = to_regional_code(language_hint) if language_hint else "en-IN"

    def _recognize(wav_bytes: bytes) -> str:
        recognizer = sr.Recognizer()
        with sr.AudioFile(io.BytesIO(wav_bytes)) as source:
            audio = recognizer.record(source)
        return recognizer.recognize_google(audio, language=recog_lang)

    try:
        transcript = _recognize(audio_bytes)
    except Exception:
        try:
            from pydub import AudioSegment  # noqa: PLC0415

            seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
            buf = io.BytesIO()
            seg.set_channels(1).set_frame_rate(16000).export(buf, format="wav")
            transcript = _recognize(buf.getvalue())
        except Exception as e:  # pragma: no cover - env dependent
            raise RuntimeError(f"Google ASR could not decode audio: {e}")

    transcript = (transcript or "").strip()
    if not transcript:
        raise RuntimeError("Google returned empty transcript")
    return transcript, language_hint, None


_ASR_BACKENDS = {
    "sarvam": _asr_sarvam,
    "groq": _asr_groq,
    "whisper": _asr_whisper,
    "google": _asr_google,
}


# ════════════════════════════════════════════════════════════════════════
# TTS BACKENDS
# ════════════════════════════════════════════════════════════════════════
# Each backend is a callable(text, bare_lang_code) -> bytes.  Raises on
# failure.  The returned audio container differs per backend (Sarvam=WAV,
# gTTS=MP3); the endpoint just base64s whatever it gets and the browser
# <audio> element sniffs the format.


def _tts_sarvam(text: str, lang: str) -> bytes:
    if not SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY not set")
    payload = {
        "inputs": [text],
        "target_language_code": to_regional_code(lang),
        "speaker": SARVAM_TTS_SPEAKER,
        "model": SARVAM_TTS_MODEL,
    }
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json",
    }
    resp = requests.post(
        SARVAM_TTS_URL, json=payload, headers=headers, timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    audios = resp.json().get("audios") or []
    if not audios:
        raise RuntimeError("Sarvam TTS returned no audio")
    return base64.b64decode(audios[0])


def _tts_gtts(text: str, lang: str) -> bytes:
    from gtts import gTTS  # noqa: PLC0415

    # gTTS uses bare ISO codes; it has no en-IN, just "en".
    code = (lang or "en").split("-")[0]
    try:
        speaker = gTTS(text=text, lang=code)
    except ValueError:
        speaker = gTTS(text=text, lang="en")
    buf = io.BytesIO()
    speaker.write_to_fp(buf)
    data = buf.getvalue()
    if not data:
        raise RuntimeError("gTTS produced no audio")
    return data


_TTS_BACKENDS = {
    "sarvam": _tts_sarvam,
    "gtts": _tts_gtts,
}


# ════════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ════════════════════════════════════════════════════════════════════════
# The fallback chain answers "give me *a* transcript".  The orchestrator
# answers "given several transcripts that disagree about the language,
# give me the *right* one".  It:
#
#   1. runs every configured ensemble backend in parallel;
#   2. for each result, reconciles a language from the transcript text
#      (script + langdetect), independent of what the engine claimed;
#   3. holds a weighted vote across all signals to pick ONE language;
#   4. picks the transcript that best matches that language — preferring
#      Sarvam for Indic languages and Whisper/Groq for the rest;
#   5. returns the refined transcript + language + a full breakdown.


class _AsrResult:
    __slots__ = ("backend", "transcript", "engine_lang", "engine_conf",
                 "reconciled_lang", "script_lang", "error")

    def __init__(self, backend: str):
        self.backend = backend
        self.transcript: Optional[str] = None
        self.engine_lang: Optional[str] = None
        self.engine_conf: Optional[float] = None
        self.reconciled_lang: Optional[str] = None
        self.script_lang: Optional[str] = None
        self.error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return bool(self.transcript) and self.error is None

    def as_dict(self) -> dict:
        return {
            "backend": self.backend,
            "ok": self.ok,
            "transcript": self.transcript,
            "engine_language": self.engine_lang,
            "engine_confidence": self.engine_conf,
            "reconciled_language": self.reconciled_lang,
            "script_language": self.script_lang,
            "error": self.error,
        }


def _run_one(
    name: str, audio_bytes: bytes, language_hint: Optional[str] = None,
) -> _AsrResult:
    res = _AsrResult(name)
    backend = _ASR_BACKENDS.get(name)
    if backend is None:
        res.error = "unknown backend"
        return res
    try:
        transcript, raw_lang, conf = backend(audio_bytes, language_hint)
        res.transcript = transcript
        res.engine_lang = bare_code(raw_lang)
        res.engine_conf = conf
        res.script_lang = script_language(transcript)
        # Fall back to the citizen's selected language only when the
        # engine offered no guess of its own.
        res.reconciled_lang = reconcile_language(
            transcript, raw_lang or language_hint, conf,
        )
    except Exception as e:  # noqa: BLE001
        res.error = str(e)
        logger.warning("ASR backend %s failed: %s", name, e)
    return res


def _gather_ensemble(
    audio_bytes: bytes, language_hint: Optional[str] = None,
) -> list[_AsrResult]:
    names = _chain("ASR_ENSEMBLE", os.getenv("ASR_ENSEMBLE") or DEFAULT_ASR_ENSEMBLE)
    # de-dupe, preserve order
    seen: set[str] = set()
    names = [n for n in names if not (n in seen or seen.add(n))]
    if not names:
        return []
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        return list(pool.map(
            lambda n: _run_one(n, audio_bytes, language_hint), names,
        ))


def _vote_language(
    results: list[_AsrResult], language_hint: Optional[str] = None,
) -> tuple[str, dict[str, float]]:
    """Weighted vote across every language signal we have.

    Weights (tuned so a clear script always wins, and a lone confident
    engine cannot override agreement between the others):

      • transcript Unicode script .......... 3.0   (near-certain)
      • citizen-selected language hint ..... 2.0
      • reconciled language per engine ..... 1.0 + engine_conf
      • raw engine guess ................... 0.5
      • langdetect consensus across texts .. up to 1.5
      • Sarvam bonus for an Indic vote ..... +0.75
      • Whisper/Groq bonus for a non-Indic . +0.5
    """
    scores: dict[str, float] = {}

    def add(lang: Optional[str], w: float) -> None:
        lang = bare_code(lang)
        if lang:
            scores[lang] = scores.get(lang, 0.0) + w

    add(language_hint, 2.0)

    combined_ld: dict[str, float] = {}
    for r in results:
        if not r.ok:
            continue
        add(r.script_lang, 3.0)
        add(r.reconciled_lang, 1.0 + (r.engine_conf or 0.0))
        add(r.engine_lang, 0.5)
        if r.backend == "sarvam" and is_indic(r.reconciled_lang):
            add(r.reconciled_lang, 0.75)
        if r.backend in ("whisper", "groq") and not is_indic(r.reconciled_lang):
            add(r.reconciled_lang, 0.5)
        for lang, prob in langdetect_scores(r.transcript).items():
            combined_ld[lang] = combined_ld.get(lang, 0.0) + prob

    if combined_ld:
        best_ld = max(combined_ld, key=combined_ld.get)
        add(best_ld, min(1.5, combined_ld[best_ld]))

    if not scores:
        return "en", {}
    winner = max(scores, key=scores.get)
    return winner, scores


def _pick_transcript(results: list[_AsrResult], language: str) -> _AsrResult:
    """Choose the transcript that best represents ``language``."""
    ok = [r for r in results if r.ok]
    if not ok:
        raise RuntimeError("no successful ASR result")

    # Engine preference order depends on the language family.
    if is_indic(language):
        pref = ["sarvam", "groq", "whisper", "google"]
    else:
        pref = ["groq", "whisper", "sarvam", "google"]

    def key(r: _AsrResult) -> tuple:
        matches_lang = r.reconciled_lang == language or r.script_lang == language
        script_ok = r.script_lang is None or r.script_lang == language
        try:
            pref_rank = -pref.index(r.backend)
        except ValueError:
            pref_rank = -99
        return (
            matches_lang,          # correct language first
            script_ok,             # never a wrong-script transcript
            pref_rank,             # then engine preference
            len(r.transcript),     # then the most complete transcript
        )

    return max(ok, key=key)


def orchestrate_transcription(
    audio_bytes: bytes, language_hint: Optional[str] = None,
) -> dict:
    """Full ensemble transcription.  Never raises.

    Returns a dict:
      {
        "ok": bool,
        "transcript": str | None,
        "language": str,               # bare ISO code, refined
        "language_scores": {lang: weight},
        "chosen_backend": str | None,
        "agreement": float,            # 0..1, how much engines agreed on lang
        "results": [ per-engine dict, ... ],
        "error": str | None,
      }
    """
    results = _gather_ensemble(audio_bytes, language_hint)
    good = [r for r in results if r.ok]
    if not good:
        errs = "; ".join(f"{r.backend}: {r.error}" for r in results) or "none ran"
        return {
            "ok": False, "transcript": None, "language": language_hint or "en",
            "language_scores": {}, "chosen_backend": None, "agreement": 0.0,
            "results": [r.as_dict() for r in results],
            "error": f"all ensemble backends failed — {errs}",
        }

    language, scores = _vote_language(results, language_hint)
    chosen = _pick_transcript(results, language)

    langs = [r.reconciled_lang for r in good if r.reconciled_lang]
    agreement = (langs.count(language) / len(langs)) if langs else 0.0

    logger.info(
        "ASR orchestrated: %d/%d engines, lang=%s (agreement %.0f%%) via %s",
        len(good), len(results), language, agreement * 100, chosen.backend,
    )
    return {
        "ok": True,
        "transcript": chosen.transcript,
        "language": language,
        "language_scores": {k: round(v, 3) for k, v in sorted(
            scores.items(), key=lambda kv: -kv[1])},
        "chosen_backend": chosen.backend,
        "agreement": round(agreement, 3),
        "results": [r.as_dict() for r in results],
        "error": None,
    }


# ════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ════════════════════════════════════════════════════════════════════════


def _transcribe_fallback(audio_bytes: bytes, language_hint: Optional[str] = None):
    errors: list[str] = []
    for name in _chain("ASR_BACKENDS", DEFAULT_ASR_CHAIN):
        backend = _ASR_BACKENDS.get(name)
        if backend is None:
            logger.warning("Unknown ASR backend %r — skipping", name)
            continue
        try:
            transcript, raw_lang, conf = backend(audio_bytes, language_hint)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
            logger.warning("ASR backend %s failed: %s", name, e)
            continue
        lang = reconcile_language(transcript, raw_lang or language_hint, conf)
        logger.info(
            "ASR ok via %s: engine_lang=%s conf=%s hint=%s -> final_lang=%s len=%d",
            name, raw_lang, conf, language_hint, lang, len(transcript),
        )
        return transcript, lang, name
    detail = "; ".join(errors) if errors else "no ASR backend configured"
    return None, f"Transcription failed — {detail}", None


def transcribe_audio_detailed(
    audio_bytes: bytes, language_hint: Optional[str] = None,
) -> dict:
    """Transcribe and return the full refinement breakdown.

    ``language_hint`` is a bare ISO code the citizen picked in the UI
    (``None`` = auto-detect).  It is passed to every engine and given a
    vote, but the transcript's own script can still override it.

    Honours ``ASR_MODE`` (``fallback`` | ``orchestrate``).  In fallback
    mode the ``results`` list is empty (only one engine ran).
    """
    language_hint = bare_code(language_hint)
    if not audio_bytes:
        return {"ok": False, "transcript": None, "language": language_hint or "en",
                "language_scores": {}, "chosen_backend": None, "agreement": 0.0,
                "results": [], "error": "Empty audio."}

    mode = (os.getenv("ASR_MODE") or DEFAULT_ASR_MODE).strip().lower()
    if mode == "orchestrate":
        return orchestrate_transcription(audio_bytes, language_hint)

    transcript, lang_or_err, backend = _transcribe_fallback(audio_bytes, language_hint)
    if transcript is None:
        return {"ok": False, "transcript": None, "language": language_hint or "en",
                "language_scores": {}, "chosen_backend": None,
                "agreement": 0.0, "results": [], "error": lang_or_err}
    return {"ok": True, "transcript": transcript, "language": lang_or_err,
            "language_scores": {}, "chosen_backend": backend,
            "agreement": 1.0, "results": [], "error": None}


def transcribe_audio(
    audio_bytes: bytes, language_hint: Optional[str] = None,
) -> Union[Tuple[str, str], Tuple[None, str]]:
    """Transcribe audio to text.

    Backwards-compatible wrapper around ``transcribe_audio_detailed``.

    Returns:
        On success: ``(transcript, language_code)`` — a bare ISO 639-1
        code reconciled against the transcript, not merely echoed from the
        engine.  In ``orchestrate`` mode this is the cross-checked,
        vote-refined language.
        On failure: ``(None, error_message)``.
    """
    detail = transcribe_audio_detailed(audio_bytes, language_hint)
    if not detail.get("ok"):
        return None, detail.get("error") or "Transcription failed."
    return detail["transcript"], detail["language"]


def synthesize_speech(
    text: str,
    language_code: str = "en",
) -> Optional[bytes]:
    """Convert text to speech, trying each backend in ``TTS_BACKENDS``.

    Returns audio bytes (WAV from Sarvam, MP3 from gTTS) on success, or
    ``None`` if every backend fails.  TTS is a nicety — callers must treat
    ``None`` as "just skip playback".
    """
    if not text or not text.strip():
        return None

    bare = (language_code or "en").split("-")[0]
    for name in _chain("TTS_BACKENDS", DEFAULT_TTS_CHAIN):
        backend = _TTS_BACKENDS.get(name)
        if backend is None:
            logger.warning("Unknown TTS backend %r — skipping", name)
            continue
        try:
            audio = backend(text, bare)
            if audio:
                logger.info("TTS ok via %s (%d bytes)", name, len(audio))
                return audio
        except Exception as e:  # noqa: BLE001 - non-fatal, try next
            logger.warning("TTS backend %s failed: %s", name, e)

    logger.warning("All TTS backends failed — skipping confirmation audio")
    return None


def list_backends() -> dict:
    """Introspection for a health endpoint / ops dashboard.

    Reports the configured chain order and whether each backend's
    dependencies are actually importable / configured right now.
    """
    def _importable(mod: str) -> bool:
        import importlib.util
        return importlib.util.find_spec(mod) is not None

    asr_status = {
        "sarvam": bool(SARVAM_API_KEY),
        "groq": bool(GROQ_API_KEY),
        "whisper": _importable("faster_whisper"),
        "google": _importable("speech_recognition"),
    }
    tts_status = {
        "sarvam": bool(SARVAM_API_KEY),
        "gtts": _importable("gtts"),
    }
    return {
        "asr": {
            "mode": (os.getenv("ASR_MODE") or DEFAULT_ASR_MODE).strip().lower(),
            "chain": _chain("ASR_BACKENDS", DEFAULT_ASR_CHAIN),
            "ensemble": _chain("ASR_ENSEMBLE", os.getenv("ASR_ENSEMBLE")
                               or DEFAULT_ASR_ENSEMBLE),
            "available": asr_status,
            "sarvam_endpoint": SARVAM_ASR_URL,
            "sarvam_model": SARVAM_ASR_MODEL,
        },
        "tts": {
            "chain": _chain("TTS_BACKENDS", DEFAULT_TTS_CHAIN),
            "available": tts_status,
            "sarvam_model": SARVAM_TTS_MODEL,
        },
        "supported_languages": SUPPORTED_LANGUAGES,
        "language_reconciliation": "script + langdetect cross-check on every transcript",
    }


# Languages offered in the UI language picker.  Bare ISO code → English
# name + endonym.  Covers what Sarvam saarika + bulbul support today.
SUPPORTED_LANGUAGES = [
    {"code": "auto", "name": "Auto-detect", "native": "Auto"},
    {"code": "en", "name": "English", "native": "English"},
    {"code": "hi", "name": "Hindi", "native": "हिन्दी"},
    {"code": "mr", "name": "Marathi", "native": "मराठी"},
    {"code": "bn", "name": "Bengali", "native": "বাংলা"},
    {"code": "ta", "name": "Tamil", "native": "தமிழ்"},
    {"code": "te", "name": "Telugu", "native": "తెలుగు"},
    {"code": "kn", "name": "Kannada", "native": "ಕನ್ನಡ"},
    {"code": "ml", "name": "Malayalam", "native": "മലയാളം"},
    {"code": "gu", "name": "Gujarati", "native": "ગુજરાતી"},
    {"code": "pa", "name": "Punjabi", "native": "ਪੰਜਾਬੀ"},
    {"code": "or", "name": "Odia", "native": "ଓଡ଼ିଆ"},
    {"code": "as", "name": "Assamese", "native": "অসমীয়া"},
    {"code": "ur", "name": "Urdu", "native": "اردو"},
]
