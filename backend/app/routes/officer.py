"""
Officer-facing routes.

Endpoints:
  GET  /officer/complaints              — all complaints assigned to this officer's department
  PUT  /officer/complaints/{id}/status  — update complaint status
  POST /officer/complaints/{id}/comment — add an internal comment / update
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter

from app.schemas import (
    ComplaintBrief,
    ComplaintOut,
    StatusUpdate,
    OfficerComment,
    TimelineEntry,
)

router = APIRouter()


@router.get("/complaints", response_model=List[ComplaintBrief])
def officer_complaints() -> list:
    """List complaints assigned to the current officer's department."""
    # TODO: filter by officer's department_id from auth context
    return [
        {
            "id": 1,
            "title": "Broken street light on MG Road",
            "status": "assigned",
            "priority_level": "high",
            "category_name": "Street Light",
            "created_at": datetime.utcnow(),
        }
    ]


@router.put("/complaints/{complaint_id}/status", response_model=ComplaintOut)
def update_complaint_status(complaint_id: int, payload: StatusUpdate) -> dict:
    """Update the status of a complaint and optionally add a comment."""
    # TODO: update DB, create ComplaintUpdate entry, recalculate SLA
    now = datetime.utcnow()
    return {
        "id": complaint_id,
        "title": "Updated complaint",
        "description": "Status was updated",
        "status": payload.status,
        "priority_level": "high",
        "priority_score": 0.7,
        "priority_reasons": ["Near other open complaints"],
        "category_name": "Street Light",
        "department_name": "Electrical",
        "location_lat": 28.6139,
        "location_lng": 77.2090,
        "address": "MG Road",
        "ward": "Ward 5",
        "language": "en",
        "created_at": now,
        "updated_at": now,
        "resolved_at": now if payload.status == "resolved" else None,
        "sla_deadline": now,
    }


@router.post("/complaints/{complaint_id}/comment", response_model=TimelineEntry)
def add_officer_comment(complaint_id: int, payload: OfficerComment) -> dict:
    """Add an officer comment to the complaint timeline."""
    # TODO: insert ComplaintUpdate row
    return {
        "id": 1,
        "status": None,
        "comment": payload.comment,
        "updated_by_name": "Officer Singh",
        "created_at": datetime.utcnow(),
    }
