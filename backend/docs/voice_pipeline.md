# Voice intake — ASR / TTS pipeline

The voice complaint endpoint (`POST /complaints/voice`) turns audio into a
complaint. It now runs an **ordered fallback chain** of engines instead of a
single provider, and it **no longer trusts the ASR engine's language guess** —
every transcript's language is re-derived from the text.

## Why the change

Sarvam transcribes Indic audio well but its automatic *language detection* is
weak on short / noisy / code-mixed clips, and the cloud API occasionally times
out. So:

1. **Native-script transcription** — Sarvam ASR now calls `/speech-to-text`
   (`saarika:v2.5`), which transcribes in the language spoken. The old code used
   `/speech-to-text-translate`, which **always returns an English translation** —
   that is why Marathi / Tamil / Bengali complaints "only worked for Hindi and
   English": every clip came back as English text tagged `en`.
2. **Fallback** — if Sarvam fails, the next engine in the chain is tried.
3. **Language reconciliation** — `app/ml/language.reconcile_language()` takes the
   transcript + the engine's guess (+ confidence if available) and decides the
   final code by:
   - dominant **Unicode script** (Tamil block → `ta`, etc.) — trusted absolutely;
   - **Hindi / Marathi / Nepali disambiguation** within Devanagari
     (`devanagari_language()` — the letter `ळ` and marker words like `आहे`,
     `नाही` flag Marathi; `छ`, `भयो` flag Nepali);
   - a plain-**English lexical check** for Latin-script text;
   - **langdetect** (seeded, deterministic) when there is enough text;
   - only then the engine's own guess.
4. **Citizen language hint** — the UI language picker (`GET /complaints/languages`)
   sends a bare ISO code that is forwarded to every engine (Sarvam
   `language_code`, Whisper `language`, Groq `language`, Google `language`) and
   given a vote — but the transcript's own script can still override it.

## Configuration (`.env`)

```
SARVAM_ASR_URL=https://api.sarvam.ai/speech-to-text   # NOT ...-translate
SARVAM_ASR_MODEL=saarika:v2.5
SARVAM_TTS_MODEL=bulbul:v2
SARVAM_TTS_SPEAKER=anushka
ASR_BACKENDS=sarvam,groq,whisper   # ordered, comma-separated
TTS_BACKENDS=sarvam,gtts
GROQ_API_KEY=...                   # for the `groq` backend
GROQ_ASR_MODEL=whisper-large-v3-turbo
WHISPER_MODEL_SIZE=small           # tiny|base|small|medium|large-v3 (small is weak on Marathi — use medium+)
VOICE_HTTP_TIMEOUT=30
```

Check what is live: `GET /complaints/voice/backends`.

## Two modes: `fallback` vs `orchestrate`

`ASR_MODE=fallback` (default) — run `ASR_BACKENDS` in order, first success wins.
One call, fast. Fine when the language usually comes out right.

`ASR_MODE=orchestrate` — the refined pipeline. Runs **every** engine in
`ASR_ENSEMBLE` *in parallel*, then:

1. re-derives each transcript's language from its **own text** (Unicode script
   + langdetect), ignoring what the engine claimed;
2. holds a **weighted vote** across all signals —
   script `×3.0`, each engine's reconciled guess `×(1 + confidence)`, raw engine
   guess `×0.5`, langdetect consensus `×≤1.5`, plus a bias term (Sarvam favoured
   for Indic, Whisper/Groq for the rest);
3. picks the transcript that **best matches the winning language** — preferring
   Sarvam's text for Indic languages, Groq/Whisper's for everything else.

The voice response then carries a `refinement` object: the per-engine
transcripts, the language-score table, `chosen_backend`, and `agreement` (0–1,
how many engines landed on the winning language).

## Bilingual "We heard …"

The voice response also carries **`transcript_english`** — an English rendering
of the transcript, so the confirmation screen shows both the spoken language and
English ("We heard (mr): … / In English: …"), and officers who don't read the
language still get a usable copy.

- `app/ml/translation.translate_text()` — Sarvam `/translate`
  (`sarvam-translate:v1`, or `mayura:v1` with `source=auto` when the language is
  unknown), falling back to `deep-translator`'s GoogleTranslator, then `None`.
- `None` when the transcript is already English or every backend failed — the UI
  just omits the second line.
- Adds one API call (~0.3–1 s) to the voice path; input is capped at 1900 chars.
- `SARVAM_TRANSLATE_MODEL` in `.env` picks the model.

Example: Sarvam mis-tags Hindi audio as `en-IN`, Groq says `hi`, local Whisper
says `hi`. Vote → `hi` (score 12.1 vs 0.5), transcript taken from Sarvam
(Devanagari, matches). The wrong language guess is outvoted instead of shipped.

Cost: N API calls instead of 1, and latency = the slowest engine. Turn it on
only for the languages/traffic where accuracy matters.

## ASR options

| name      | key? | offline | strengths | weaknesses |
|-----------|------|---------|-----------|------------|
| `sarvam`  | yes  | no  | best Indic accuracy, native-script output, 22 langs | weak lang-detect (handled), rate limits, cost |
| `groq`    | yes  | no  | Whisper large-v3 quality, extremely fast, cheap, strong multilingual | needs key, cloud dependency |
| `whisper` | no   | yes | free, private, good multilingual, gives confidence | ~1 GB model, slow on CPU, needs `faster-whisper` |
| `google`  | no   | no  | zero setup, decent English | undocumented/rate-limited, English-biased, needs `SpeechRecognition` (+ffmpeg via `pydub` for webm) |

Recommended chain: `sarvam,groq,whisper` (Indic-tuned first, fast cloud
Whisper second, offline safety net last).
Privacy-first / no-key deploy: `whisper` alone.

## TTS options

| name     | key? | quality | notes |
|----------|------|---------|-------|
| `sarvam` | yes  | natural neural voices (bulbul) | best UX, costs money |
| `gtts`   | no   | robotic but clear, all Indic langs | free, needs network, returns MP3 |

Recommended chain: `sarvam,gtts`.

## Adding another engine

Add a function to `_ASR_BACKENDS` / `_TTS_BACKENDS` in
`app/ml/voice_intake.py` (signature documented there) and list its name in the
env chain. Nothing else changes.
