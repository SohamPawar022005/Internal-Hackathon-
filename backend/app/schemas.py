"""
Pydantic request / response schemas for NIVARAN.

╔══════════════════════════════════════════════════════════════════════╗
║  SCHEMA FIELD REFERENCE (mirrors models.py — see that header)      ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  UserOut           → id, name, email, role, department_id           ║
║  LoginRequest      → role (citizen|officer|admin), name             ║
║                                                                    ║
║  ComplaintCreate   → title, description, location_lat,              ║
║                      location_lng, address, ward                   ║
║  ComplaintOut       → all Complaint fields + category_name,         ║
║                      department_name, priority, sla info            ║
║  ComplaintBrief     → id, title, status, priority_level, created_at ║
║                                                                    ║
║  TimelineEntry     → id, status, comment, updated_by_name,         ║
║                      created_at                                    ║
║                                                                    ║
║  StatusUpdate      → status, comment                               ║
║  OfficerComment    → comment                                       ║
║                                                                    ║
║  DashboardStats    → total, resolved, pending, avg_resolution_hrs  ║
║  DeptStat          → department, count, resolved                   ║
║  CategoryStat      → category, count                               ║
║                                                                    ║
║  GeoComplaint      → id, lat, lng, status, category, priority      ║
║  HeatmapPoint      → lat, lng, weight                              ║
║                                                                    ║
║  SimilarComplaintOut → id, title, similarity_score, status          ║
║  PriorityOut        → level, score, reasons[]                      ║
║                                                                    ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


# ── Auth ───────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """Fake login — just picks a role."""
    role: str = "citizen"
    name: str = "Test User"


class UserOut(BaseModel):
    """Public user representation."""
    id: int
    name: str
    email: str
    role: str
    department_id: Optional[int] = None

    class Config:
        from_attributes = True


# ── Complaints ─────────────────────────────────────────────────────────

class ComplaintCreate(BaseModel):
    """Payload for submitting a new complaint."""
    title: str
    description: str
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    address: Optional[str] = None
    ward: Optional[str] = None
    # Optional language code the citizen picked ("hi", "mr", …). When
    # omitted the backend detects it from the text.
    language: Optional[str] = None


class ComplaintBrief(BaseModel):
    """Compact complaint summary for lists."""
    id: int
    title: str
    status: str
    priority_level: Optional[str] = None
    category_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ComplaintOut(BaseModel):
    """Full complaint detail."""
    id: int
    title: str
    description: str
    status: str
    priority_level: Optional[str] = None
    priority_score: Optional[float] = None
    priority_reasons: List[str] = []
    category_name: Optional[str] = None
    department_name: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    address: Optional[str] = None
    ward: Optional[str] = None
    language: str = "en"
    is_crisis: bool = False
    routing: Optional["RouteResult"] = None
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    sla_deadline: Optional[datetime] = None

    class Config:
        from_attributes = True


class TimelineEntry(BaseModel):
    """Single entry in a complaint's update timeline."""
    id: int
    status: Optional[str] = None
    comment: Optional[str] = None
    updated_by_name: Optional[str] = None
    created_at: datetime


# ── Officer ────────────────────────────────────────────────────────────

class StatusUpdate(BaseModel):
    """Payload for changing complaint status."""
    status: str
    comment: Optional[str] = None


class OfficerComment(BaseModel):
    """Payload for adding an officer comment."""
    comment: str


# ── Admin Dashboard ───────────────────────────────────────────────────

class DashboardStats(BaseModel):
    """Top-level dashboard numbers."""
    total: int
    resolved: int
    pending: int
    avg_resolution_hrs: float


class DeptStat(BaseModel):
    """Per-department complaint count."""
    department: str
    count: int
    resolved: int


class CategoryStat(BaseModel):
    """Per-category complaint count."""
    category: str
    count: int


# ── Geo ────────────────────────────────────────────────────────────────

class GeoComplaint(BaseModel):
    """Complaint with coordinates for map markers."""
    id: int
    lat: float
    lng: float
    status: str
    category: Optional[str] = None
    priority_level: Optional[str] = None


class HeatmapPoint(BaseModel):
    """Single point for the heatmap layer."""
    lat: float
    lng: float
    weight: float = 1.0


# ── ML ─────────────────────────────────────────────────────────────────

class SimilarComplaintOut(BaseModel):
    """A complaint identified as similar to the current one."""
    id: int
    title: str
    similarity_score: float
    status: str


class PriorityOut(BaseModel):
    """ML-computed priority assessment."""
    level: str
    score: float
    reasons: List[str]


# ── Routing ────────────────────────────────────────────────────────────

class RoutePreviewRequest(BaseModel):
    """Text to run through the router without persisting anything."""
    title: Optional[str] = None
    description: Optional[str] = None
    language: Optional[str] = None


class RouteAlternative(BaseModel):
    category: str
    department: str
    score: float


class RouteResult(BaseModel):
    """Output of ml.classifier.route_complaint()."""
    category: str
    department: str
    department_key: str
    confidence: float
    matched_keywords: List[str] = []
    is_crisis: bool = False
    crisis_type: Optional[str] = None
    crisis_department: Optional[str] = None
    urgency: str = "medium"
    urgency_signals: List[str] = []
    alternatives: List[RouteAlternative] = []
    language: Optional[str] = None


# ── Voice ──────────────────────────────────────────────────────────────

class VoiceComplaintResponse(BaseModel):
    """Response from the voice complaint endpoint.

    Wraps the normal ComplaintOut with the transcript the STT produced
    and an optional base64-encoded confirmation audio clip.
    """
    complaint: ComplaintOut
    transcript: str
    # English rendering of `transcript`, when it was spoken in another
    # language and translation succeeded. None otherwise.
    transcript_english: Optional[str] = None
    detected_language: str = "en"
    confirmation_audio_base64: Optional[str] = None
    # Present when ASR_MODE=orchestrate: per-engine transcripts, the
    # weighted language vote, which engine's text was chosen, and how much
    # the engines agreed (0..1). Useful for debugging language accuracy.
    refinement: Optional[Dict[str, Any]] = None
    routing: Optional[RouteResult] = None


# Resolve the forward reference ComplaintOut → RouteResult now that
# RouteResult is defined.
ComplaintOut.model_rebuild()
