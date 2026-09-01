"""
Language detection utilities.

Two problems this module solves:

  1. Plain-text language detection for typed complaints (`detect_language`).
  2. Reconciling the language guessed by an ASR engine (Sarvam, Whisper,
     Groq, Google) with what the transcript text actually looks like
     (`reconcile_language`).  ASR language detection is often wrong on
     short, code-mixed or noisy audio, so we cross-check it against the
     Unicode script and against `langdetect`.

Everything returns a bare ISO 639-1 code (``"en"``, ``"hi"``, ``"mr"`` …).
Callers that need a regional tag (``"mr-IN"``) use `to_regional_code`.

Devanagari note
───────────────
Hindi, Marathi, Nepali, Konkani and Sanskrit all share the Devanagari
block, so "this string is Devanagari" is *not* the same as "this string
is Hindi".  `devanagari_language()` disambiguates them with a small set
of high-precision marker words / letters (e.g. the letter ``ळ`` is
everyday Marathi but almost absent from Hindi).  This is what fixed
Marathi complaints being filed as Hindi.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from langdetect import DetectorFactory, LangDetectException
    from langdetect import detect_langs as _ld_detect_langs

    DetectorFactory.seed = 0  # deterministic
    _HAS_LANGDETECT = True
except Exception:  # pragma: no cover
    _HAS_LANGDETECT = False

    class LangDetectException(Exception):
        pass


DEFAULT_LANGUAGE = "en"

# Languages Sarvam is specifically tuned for (and Whisper/Groq weaker on
# for short clips) — used to bias the orchestrator's transcript choice.
INDIC_LANGUAGES = {
    "hi", "mr", "bn", "ta", "te", "kn", "ml", "gu", "pa", "or",
    "as", "ur", "ne", "sa", "kok", "mai", "sd", "sat", "ks", "doi",
}

# Bare code → Sarvam / gTTS regional tag.
_REGIONAL = {
    "en": "en-IN", "hi": "hi-IN", "ta": "ta-IN", "te": "te-IN",
    "kn": "kn-IN", "ml": "ml-IN", "bn": "bn-IN", "gu": "gu-IN",
    "mr": "mr-IN", "pa": "pa-IN", "or": "od-IN", "as": "as-IN",
    "ur": "ur-IN", "ne": "ne-IN", "kok": "kok-IN", "sa": "sa-IN",
    "mai": "mai-IN",
}


def to_regional_code(code: Optional[str]) -> str:
    """``"mr"`` → ``"mr-IN"``; pass through anything already regional."""
    if not code:
        return "en-IN"
    code = code.strip()
    if "-" in code:
        return code
    return _REGIONAL.get(code.lower(), f"{code.lower()}-IN")


# ── Unicode script → language ───────────────────────────────────────────
_SCRIPT_RANGES = [
    ("bn", r"ঀ-৿"),   # Bengali / Assamese
    ("ta", r"஀-௿"),   # Tamil
    ("te", r"ఀ-౿"),   # Telugu
    ("kn", r"ಀ-೿"),   # Kannada
    ("ml", r"ഀ-ൿ"),   # Malayalam
    ("gu", r"઀-૿"),   # Gujarati
    ("pa", r"਀-੿"),   # Gurmukhi (Punjabi)
    ("or", r"଀-୿"),   # Odia
    ("ur", r"؀-ۿ"),   # Arabic block (Urdu)
    ("hi", r"ऀ-ॿ"),   # Devanagari (Hindi / Marathi / Nepali / …)
]
_SCRIPT_PATTERNS = [(lang, re.compile(f"[{rng}]")) for lang, rng in _SCRIPT_RANGES]

_DEVANAGARI_LANGS = {"hi", "mr", "ne", "sa", "kok", "mai"}

# ── Devanagari disambiguation markers ──────────────────────────────────
# Marathi: the retroflex ``ळ`` and ``ऱ``, plus common function words.
_MR_LETTERS = re.compile(r"[ळऴ]")
_MR_WORDS = {
    "आहे", "आहेत", "नाही", "नाहीये", "मला", "तुला", "त्याला", "आम्ही",
    "तुम्ही", "आपण", "त्यांनी", "काय", "कुठे", "इथे", "तिथे", "झाले",
    "झाली", "केले", "पाहिजे", "होते", "आणि", "किंवा", "म्हणून", "माझ्या",
    "आमच्या", "रस्ता", "रस्त्यावर", "पाणी", "गटार", "कचरा", "वीज",
    "दिवा", "तक्रार", "नगरपालिका", "परिसरात", "गेल्या", "दिवसांपासून",
    "खूप", "समस्या", "आमच्या",
}
# Nepali markers.
_NE_WORDS = {
    "छ", "छन्", "छैन", "हो", "होइन", "गरेको", "भयो", "मलाई", "हामी",
    "तपाईं", "अनि", "मा", "को", "लाई", "हुन्छ", "गर्नु", "पर्यो",
    "बाटो", "पानी", "बिजुली", "फोहोर", "समस्या", "छ।",
}
# Hindi markers (used to positively confirm Hindi vs the others).
_HI_WORDS = {
    "है", "हैं", "नहीं", "मैं", "आप", "हम", "क्या", "यहाँ", "वहाँ",
    "गया", "किया", "चाहिए", "और", "सड़क", "पानी", "बिजली", "कचरा",
    "नाली", "शिकायत", "कृपया", "हमारे", "मेरे", "रहा", "रही", "दिन",
    "से", "को", "में", "का", "की", "के",
}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[^\s,।!?.:;\"'()]+", text or "")


def devanagari_language(text: str) -> str:
    """Best guess among Devanagari languages: ``"hi" | "mr" | "ne"``.

    Combines a marker-word count with langdetect (which does distinguish
    the three).  Defaults to Hindi — the most common — when nothing
    stands out.
    """
    toks = set(_tokens(text))
    mr = len(toks & _MR_WORDS) + 2 * len(_MR_LETTERS.findall(text))
    ne = len(toks & _NE_WORDS)
    hi = len(toks & _HI_WORDS)

    ld = langdetect_scores(text)
    hi += 3.0 * ld.get("hi", 0.0)
    mr += 3.0 * ld.get("mr", 0.0)
    ne += 3.0 * ld.get("ne", 0.0)

    best, score = max((("hi", hi), ("mr", mr), ("ne", ne)), key=lambda kv: kv[1])
    return best if score > 0 else "hi"


def _dominant_script_language(text: str) -> Optional[str]:
    """Language of the dominant non-Latin script, or ``None``.

    The winning script must cover >= 15% of the alphabetic characters so
    a stray loanword doesn't flip the result.  Devanagari is resolved to
    hi/mr/ne via `devanagari_language`.
    """
    counts: dict[str, int] = {}
    for lang, pattern in _SCRIPT_PATTERNS:
        n = len(pattern.findall(text))
        if n:
            counts[lang] = n
    if not counts:
        return None

    alpha = sum(1 for ch in text if ch.isalpha()) or 1
    lang, n = max(counts.items(), key=lambda kv: kv[1])
    if n / alpha < 0.15:
        return None
    if lang == "hi":
        return devanagari_language(text)
    return lang


# ── langdetect helpers ─────────────────────────────────────────────────
def langdetect_scores(text: str) -> dict[str, float]:
    """``{lang: probability}`` from langdetect (empty on failure)."""
    if not _HAS_LANGDETECT or not (text or "").strip():
        return {}
    try:
        return {r.lang: float(r.prob) for r in _ld_detect_langs(text)}
    except LangDetectException:
        return {}


def _langdetect_top(text: str) -> tuple[Optional[str], float]:
    scores = langdetect_scores(text)
    if not scores:
        return None, 0.0
    lang = max(scores, key=scores.get)
    return lang, scores[lang]


# ── English lexical check (Latin script) ──────────────────────────────
_LATIN_RE = re.compile(r"[A-Za-z]")
_NON_LATIN_RE = re.compile(r"[^\x00-\x7f]")
_EN_STOPWORDS = {
    "the", "is", "a", "an", "and", "or", "not", "no", "my", "our", "your",
    "there", "here", "near", "in", "on", "at", "to", "of", "for", "with",
    "was", "were", "has", "have", "please", "this", "that", "it", "are",
    "working", "since", "days", "road", "water", "light", "street", "power",
}


def _looks_english(text: str) -> bool:
    toks = re.findall(r"[a-z]+", text.lower())
    if len(toks) < 2:
        return False
    hits = sum(1 for t in toks if t in _EN_STOPWORDS)
    return hits >= 2 or hits / len(toks) >= 0.34


def _is_latin(text: str) -> bool:
    return bool(_LATIN_RE.search(text)) and not _NON_LATIN_RE.search(text)


# ── Public helpers ────────────────────────────────────────────────────
def bare_code(code: Optional[str]) -> Optional[str]:
    """``"mr-IN"`` → ``"mr"``; junk / unknown → ``None``."""
    if not code:
        return None
    code = code.strip().lower().split("-")[0].split("_")[0]
    if code in ("", "unknown", "und", "auto", "none"):
        return None
    return code


def script_language(text: str) -> Optional[str]:
    """Language implied by the dominant Unicode script (hi/mr/ne aware)."""
    return _dominant_script_language(text or "")


def is_indic(code: Optional[str]) -> bool:
    return bare_code(code) in INDIC_LANGUAGES


# ── Main entry points ─────────────────────────────────────────────────
def detect_language(text: str) -> str:
    """Detect the language of a piece of text (script → English → langdetect)."""
    text = (text or "").strip()
    if not text:
        return DEFAULT_LANGUAGE

    script_lang = _dominant_script_language(text)
    if script_lang:
        return script_lang

    if _is_latin(text) and _looks_english(text):
        return "en"

    word_count = len(re.findall(r"\w+", text))
    if word_count < 3:
        return DEFAULT_LANGUAGE

    lang, prob = _langdetect_top(text)
    if lang and prob >= 0.60 and word_count >= 5:
        return lang
    return DEFAULT_LANGUAGE


def reconcile_language(
    text: str,
    asr_language: Optional[str] = None,
    asr_confidence: Optional[float] = None,
) -> str:
    """Decide the final language code for an ASR transcript.

    Priority:
      1. Dominant Unicode script (Devanagari resolved to hi/mr/ne) —
         trusted absolutely; the script cannot lie about itself.
      2. Latin transcript that reads as plain English.
      3. A high-confidence ASR guess langdetect does not contradict.
      4. langdetect, when there is enough text.
      5. The ASR guess, then English.
    """
    text = (text or "").strip()
    asr_code = bare_code(asr_language)

    script_lang = _dominant_script_language(text)
    if script_lang:
        return script_lang

    if _is_latin(text) and _looks_english(text):
        return "en"

    word_count = len(re.findall(r"\w+", text))
    ld_lang, ld_prob = _langdetect_top(text)
    ld_authoritative = ld_lang is not None and ld_prob >= 0.75 and word_count >= 5

    if asr_code and asr_confidence is not None and asr_confidence >= 0.85:
        if not ld_authoritative or ld_lang == asr_code:
            return asr_code

    if ld_authoritative:
        return ld_lang
    if asr_code:
        return asr_code
    if ld_lang and ld_prob >= 0.55 and word_count >= 5:
        return ld_lang
    return DEFAULT_LANGUAGE
