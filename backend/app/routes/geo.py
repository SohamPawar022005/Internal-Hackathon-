"""
Geo/map routes.

Endpoints:
  GET /geo/complaints — all complaints with lat/lng for map markers
  GET /geo/heatmap    — weighted points for the heatmap layer
"""

from typing import List
from fastapi import APIRouter
from app.schemas import GeoComplaint, HeatmapPoint

router = APIRouter()


@router.get("/complaints", response_model=List[GeoComplaint])
def geo_complaints() -> list:
    """Return geolocated complaints for map markers."""
    # TODO: query complaints with non-null lat/lng
    return [
        {"id": 1, "lat": 28.6139, "lng": 77.2090, "status": "submitted", "category": "Pothole", "priority_level": "high"},
        {"id": 2, "lat": 28.6200, "lng": 77.2150, "status": "assigned", "category": "Street Light", "priority_level": "medium"},
        {"id": 3, "lat": 28.6300, "lng": 77.2000, "status": "in_progress", "category": "Garbage", "priority_level": "low"},
    ]


@router.get("/heatmap", response_model=List[HeatmapPoint])
def heatmap_data() -> list:
    """Return weighted lat/lng points for the heatmap overlay."""
    # TODO: aggregate complaint density from DB
    return [
        {"lat": 28.6139, "lng": 77.2090, "weight": 5.0},
        {"lat": 28.6200, "lng": 77.2150, "weight": 3.0},
        {"lat": 28.6300, "lng": 77.2000, "weight": 1.0},
    ]
