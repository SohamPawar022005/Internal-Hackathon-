"""
Citizen-facing complaint routes.

Endpoints:
  POST /complaints             — submit a new complaint (text)
  POST /complaints/voice       — submit a new complaint (audio)
  GET  /complaints/my          — list current user's complaints
  GET  /complaints/track/{id}  — full detail of one complaint
  GET  /complaints/{id}/timeline — ordered status updates
"""

import base64
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas import (
    ComplaintCreate,
    ComplaintOut,
    ComplaintBrief,
    TimelineEntry,
    SimilarComplaintOut,
    PriorityOut,
    RoutePreviewRequest,
    RouteResult,
    VoiceComplaintResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Department SLA windows (days) — used to set the resolution deadline.
_DEPARTMENT_SLA_DAYS = {
    "fire": 1, "electricity": 2, "water": 2, "drainage": 3, "sewerage": 3,
    "streetlight": 5, "pwd": 7, "sanitation": 3, "health": 4, "traffic": 5,
    "horticulture": 5, "planning": 15, "pollution": 10, "animal": 3,
    "grievance": 7,
}


# ── Shared pipeline ───────────────────────────────────────────────────
# Both text and voice endpoints call this function.  It encapsulates the
# route → detect language → score priority → (persist) flow.  Do NOT
# duplicate this logic elsewhere.

def _process_complaint_submission(
    title: str,
    description: str,
    location_lat: Optional[float] = None,
    location_lng: Optional[float] = None,
    address: Optional[str] = None,
    ward: Optional[str] = None,
    detected_language: Optional[str] = None,
) -> dict:
    """Run the ML pipeline and (eventually) persist a complaint.

    Single source of truth for complaint processing — used by both
    POST /complaints (text) and POST /complaints/voice (audio→text).

    Steps:
      1. ml.language.detect_language() — unless the ASR pipeline already
         reconciled a language code for us.
      2. ml.classifier.route_complaint() — category + department, and
         crisis / emergency detection, off the complaint text.
      3. ml.priority.calculate_priority_score() — priority level + score
         + reasons, factoring the routed urgency and any crisis flag.
      4. TODO: persist to DB, generate embedding, find duplicates.

    Returns:
        Dict matching ComplaintOut schema shape, plus a "routing" block.
    """
    from app.ml.classifier import route_complaint
    from app.ml.language import detect_language
    from app.ml.priority import calculate_priority_score

    full_text = f"{title}\n{description}".strip()

    # 1. Language
    language = detected_language or detect_language(full_text)

    # 2. Routing — category, department, crisis
    routing = route_complaint(full_text, language=language)

    # 3. Priority
    now = datetime.utcnow()
    sla_days = _DEPARTMENT_SLA_DAYS.get(routing["department_key"], 7)
    sla_deadline = now + timedelta(days=sla_days)
    level, score, reasons = calculate_priority_score(
        {
            "urgency": routing["urgency"],
            "is_crisis": routing["is_crisis"],
            "crisis_type": routing["crisis_type"],
            "urgency_signals": routing["urgency_signals"],
            "category": routing["category"],
            "created_at": now,
            "sla_deadline": sla_deadline,
            "status": "submitted",
        },
        nearby_open_count=0,  # TODO: query PostGIS for nearby open complaints
    )

    # 4. TODO: persist to DB, embed, dedupe
    department = routing["department"]
    if routing["is_crisis"] and routing["crisis_department"]:
        # Emergencies are owned by the responding department, with the
        # original department co-notified (recorded in routing).
        department = routing["crisis_department"]

    return {
        "id": 1,
        "title": title,
        "description": description,
        "status": "submitted",
        "priority_level": level,
        "priority_score": score,
        "priority_reasons": reasons,
        "category_name": routing["category"],
        "department_name": department,
        "location_lat": location_lat,
        "location_lng": location_lng,
        "address": address,
        "ward": ward,
        "language": language or "en",
        "is_crisis": routing["is_crisis"],
        "routing": routing,
        "created_at": now,
        "updated_at": now,
        "resolved_at": None,
        "sla_deadline": sla_deadline,
    }


# ── Text submission ───────────────────────────────────────────────────

@router.post("/", response_model=ComplaintOut)
def submit_complaint(payload: ComplaintCreate) -> dict:
    """Accept a new complaint via text, run ML pipeline, persist to DB."""
    return _process_complaint_submission(
        title=payload.title,
        description=payload.description,
        location_lat=payload.location_lat,
        location_lng=payload.location_lng,
        address=payload.address,
        ward=payload.ward,
        detected_language=payload.language,
    )


# ── Routing preview (no persistence) ─────────────────────────────────

@router.post("/route-preview", response_model=RouteResult)
def route_preview(payload: RoutePreviewRequest) -> dict:
    """Show which category / department a complaint text would route to.

    Powers the live "this will go to …" hint on the submit form and is
    handy for testing the multilingual keyword router.
    """
    from app.ml.classifier import route_complaint
    from app.ml.language import detect_language

    text = f"{payload.title or ''}\n{payload.description or ''}".strip()
    if not text:
        raise HTTPException(status_code=422, detail="No complaint text provided.")
    language = payload.language or detect_language(text)
    return route_complaint(text, language=language)


@router.get("/languages")
def supported_languages() -> list:
    """Languages offered in the intake language picker (voice + text)."""
    from app.ml.voice_intake import SUPPORTED_LANGUAGES

    return SUPPORTED_LANGUAGES


# ── Voice submission ─────────────────────────────────────────────────

@router.post("/voice", response_model=VoiceComplaintResponse)
async def submit_voice_complaint(
    audio: UploadFile = File(..., description="Audio file (WAV/WebM/MP3)"),
    location_lat: Optional[float] = Form(None),
    location_lng: Optional[float] = Form(None),
    address: Optional[str] = Form(None),
    ward: Optional[str] = Form(None),
    language: Optional[str] = Form(
        None, description="ISO code the citizen picked, or 'auto' / omitted"
    ),
) -> dict:
    """Accept a voice complaint: transcribe → run the SAME pipeline as text.

    Flow:
      1. Read uploaded audio bytes
      2. transcribe_audio_detailed() — Sarvam native-script STT, with the
         Whisper/Groq/Google fallback chain or full orchestration, using
         the citizen's language hint
      3. If transcription fails → 422 with user-friendly message
      4. Pass transcript into _process_complaint_submission() — identical
         to what the text endpoint calls (routes to a department, detects
         crisis, scores priority)
      5. Optionally synthesize confirmation audio via TTS
      6. Return complaint + transcript + refinement + routing + audio
    """
    from app.ml.voice_intake import transcribe_audio_detailed, synthesize_speech

    hint = None if not language or language.lower() == "auto" else language.lower()

    # 1. Read audio
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=422,
            detail="Empty audio file received. Please record again.",
        )

    # 2. Transcribe (fallback chain or full orchestration, per ASR_MODE)
    asr = transcribe_audio_detailed(audio_bytes, language_hint=hint)

    # 3. Handle transcription failure
    if not asr.get("ok"):
        logger.warning(f"Voice transcription failed: {asr.get('error')}")
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not understand the audio. Please try again "
                "or use the text form."
            ),
        )

    transcript = asr["transcript"]
    lang_or_error = asr["language"]
    refinement = {
        "mode": "orchestrate" if asr.get("results") else "fallback",
        "language": asr["language"],
        "language_scores": asr.get("language_scores") or {},
        "chosen_backend": asr.get("chosen_backend"),
        "agreement": asr.get("agreement"),
        "engines": asr.get("results") or [],
    }

    # English rendering of the transcript, so "We heard …" can be shown in
    # both the spoken language and English. Best-effort — None when the
    # transcript is already English or translation is unavailable.
    transcript_english = None
    if lang_or_error and lang_or_error != "en":
        try:
            from app.ml.translation import translate_text

            transcript_english = translate_text(
                transcript, source_language=lang_or_error, target="en"
            )
        except Exception as e:  # noqa: BLE001 - non-fatal
            logger.warning(f"Transcript translation failed (non-fatal): {e}")

    # 4. Run the same pipeline as text submission
    #    Use the transcript as both title (first 80 chars) and full description
    title = transcript[:80] + ("..." if len(transcript) > 80 else "")
    complaint_data = _process_complaint_submission(
        title=title,
        description=transcript,
        location_lat=location_lat,
        location_lng=location_lng,
        address=address,
        ward=ward,
        detected_language=lang_or_error,  # this is language_code on success
    )

    # 5. Optionally synthesize confirmation audio (best-effort)
    confirmation_audio_b64 = None
    complaint_id = complaint_data.get("id", "N/A")
    confirmation_text = (
        f"Your complaint has been registered, tracking ID {complaint_id}."
    )
    try:
        tts_bytes = synthesize_speech(confirmation_text, lang_or_error)
        if tts_bytes:
            confirmation_audio_b64 = base64.b64encode(tts_bytes).decode("ascii")
    except Exception as e:
        # TTS failure is non-fatal — just skip it
        logger.warning(f"TTS synthesis failed (non-fatal): {e}")

    # 6. Return composite response
    return {
        "complaint": complaint_data,
        "transcript": transcript,
        "transcript_english": transcript_english,
        "detected_language": lang_or_error,
        "confirmation_audio_base64": confirmation_audio_b64,
        "refinement": refinement,
        "routing": complaint_data.get("routing"),
    }


@router.get("/voice/backends")
def voice_backends() -> dict:
    """Report the configured ASR/TTS fallback chain and what is available.

    Useful for ops / debugging language-detection issues — shows which
    engine actually served a request and whether Sarvam, Whisper, Google
    and gTTS are each usable right now.
    """
    from app.ml.voice_intake import list_backends

    return list_backends()


# ── Existing read endpoints (unchanged) ──────────────────────────────

@router.get("/my", response_model=List[ComplaintBrief])
def my_complaints() -> list:
    """List complaints submitted by the current user."""
    # TODO: filter by current user from auth context
    return [
        {
            "id": 1,
            "title": "Sample pothole complaint",
            "status": "submitted",
            "priority_level": "medium",
            "category_name": "Pothole",
            "created_at": datetime.utcnow(),
        }
    ]


@router.get("/track/{complaint_id}", response_model=ComplaintOut)
def track_complaint(complaint_id: int) -> dict:
    """Get full details of a single complaint by ID."""
    # TODO: fetch from DB, join category + department names
    now = datetime.utcnow()
    return {
        "id": complaint_id,
        "title": "Sample complaint",
        "description": "Placeholder description",
        "status": "submitted",
        "priority_level": "medium",
        "priority_score": 0.5,
        "priority_reasons": [],
        "category_name": "General",
        "department_name": "Public Works",
        "location_lat": 28.6139,
        "location_lng": 77.2090,
        "address": "New Delhi",
        "ward": "Ward 1",
        "language": "en",
        "created_at": now,
        "updated_at": now,
        "resolved_at": None,
        "sla_deadline": now + timedelta(days=7),
    }


@router.get("/{complaint_id}/timeline", response_model=List[TimelineEntry])
def complaint_timeline(complaint_id: int) -> list:
    """Get chronological status updates for a complaint."""
    # TODO: query ComplaintUpdate table ordered by created_at
    return [
        {
            "id": 1,
            "status": "submitted",
            "comment": "Complaint received",
            "updated_by_name": "System",
            "created_at": datetime.utcnow(),
        }
    ]
