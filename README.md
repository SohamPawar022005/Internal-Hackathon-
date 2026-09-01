# NIVARAN — AI-Based Citizen Grievance Platform

## Quick Start

```bash
# Clone and start everything
docker compose up --build

# Services:
#   Frontend  → http://localhost:5173
#   Backend   → http://localhost:8000
#   API Docs  → http://localhost:8000/docs
#   Postgres  → localhost:5432  (user: nivaran / pass: nivaran_dev)
```

## Development (without Docker)

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # edit DATABASE_URL if needed
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Features

| Feature | Status | Details |
|---------|--------|---------|
| Text complaint submission | ✅ Built | POST /complaints/ — full form, live routing preview, multilingual |
| **Voice complaint submission** | ✅ Built | POST /complaints/voice — audio → transcribe → same pipeline as text |
| **Complaint routing** | ✅ Built | Text → category → department + crisis detection (`app/ml/classifier.py`, see `docs/routing.md`) |
| **Multilingual intake** | ✅ Built | Native-script ASR + Hindi/Marathi/… detection; UI language picker (`docs/voice_pipeline.md`) |
| Officer dashboard | ✅ Stubbed | Status updates, comments |
| Admin analytics | ✅ Stubbed | KPI cards, department/category stats |
| Geo heatmap | ✅ Stubbed | Leaflet + leaflet.heat |

### Voice Intake — How It Works

1. Citizen picks a language (or "Auto-detect"), then types or taps "Speak"
2. Audio is uploaded to `POST /complaints/voice` with the language hint
3. Backend transcribes via an **ordered fallback chain** — Sarvam AI
   (`/speech-to-text`, native script), Groq-hosted Whisper, local
   faster-whisper, free Google — or, in `ASR_MODE=orchestrate`, runs several
   in parallel and cross-checks them (see `docs/voice_pipeline.md`)
4. The language is **reconciled from the transcript itself** (Unicode script +
   Hindi/Marathi/Nepali disambiguation + langdetect), not taken on trust
5. Transcript + detected language + routed department are shown for confirmation
6. On confirmation, the transcript runs the **same** route → priority pipeline
   as text complaints (`_process_complaint_submission()`)
7. Optionally a TTS confirmation clip is generated (Sarvam bulbul → gTTS fallback)

### Routing — How It Works

`app/ml/classifier.route_complaint()` maps the complaint text to a **category**
and **department** with a curated multilingual keyword map (English + Hindi +
Marathi + Romanised), and flags **emergencies** (fire, gas leak, collapse,
electrocution, flooding) — fast-tracking them to the responding department and
forcing `critical` priority. `POST /complaints/route-preview` exposes it for the
form's live "this will go to …" hint. Full details in `docs/routing.md`.

### Deviations & Honest Status

- **Sarvam endpoint**: switched from `/speech-to-text-translate` (English-only
  output — the reason non-Hindi languages "didn't work") to `/speech-to-text`.
- **faster-whisper `small`** is weak on Marathi/Telugu; set
  `WHISPER_MODEL_SIZE=medium` (or use the `groq` backend) for better vernacular.
- **TTS confirmation audio**: best-effort. If every backend fails, no audio is
  played and the frontend silently skips it.
- **Router** is rule-based keywords (no trained model / labelled data yet); it is
  accurate for common civic complaints and easy to extend per city.
- **Priority `nearby_open_count`** is still 0 (PostGIS query is a TODO).

## Project Structure

- **backend/** — FastAPI + SQLAlchemy + ML pipeline
- **backend/app/ml/voice_intake.py** — ASR chain (Sarvam/Groq/Whisper/Google) + TTS (Sarvam/gTTS) + orchestration
- **backend/app/ml/language.py** — script + langdetect language reconciliation (hi/mr/ne aware)
- **backend/app/ml/classifier.py** — complaint → category → department + crisis detection
- **backend/app/ml/priority.py** — priority level / score / reasons
- **backend/docs/** — `voice_pipeline.md`, `routing.md`
- **frontend/** — React + Vite + Tailwind + Leaflet
- **frontend/src/components/VoiceRecorder.jsx** — Browser-native audio recorder
- **frontend/src/components/{LanguagePicker,RoutingCard}.jsx** — intake language + routing display
- **docker-compose.yml** — Postgres (PostGIS) + backend + frontend

## Team Split

| Area | Owner | Key Directories |
|------|-------|----------------|
| Backend + ML | Person A | `backend/app/`, `backend/app/ml/` |
| Frontend + UI | Person B | `frontend/src/` |
