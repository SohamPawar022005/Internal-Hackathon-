"""
Admin dashboard routes.

Endpoints:
  GET /admin/dashboard/stats
  GET /admin/dashboard/department-stats
  GET /admin/dashboard/category-distribution
  GET /admin/complaints
"""

from datetime import datetime
from typing import List
from fastapi import APIRouter, Query
from app.schemas import DashboardStats, DeptStat, CategoryStat, ComplaintBrief

router = APIRouter()


@router.get("/dashboard/stats", response_model=DashboardStats)
def dashboard_stats() -> dict:
    """Aggregate KPIs across all complaints."""
    # TODO: query DB for real counts and averages
    return {"total": 150, "resolved": 87, "pending": 63, "avg_resolution_hrs": 42.5}


@router.get("/dashboard/department-stats", response_model=List[DeptStat])
def department_stats() -> list:
    """Complaint counts grouped by department."""
    # TODO: GROUP BY department_id in DB
    return [
        {"department": "Public Works", "count": 45, "resolved": 30},
        {"department": "Electrical", "count": 32, "resolved": 18},
        {"department": "Sanitation", "count": 28, "resolved": 20},
    ]


@router.get("/dashboard/category-distribution", response_model=List[CategoryStat])
def category_distribution() -> list:
    """Complaint counts grouped by category."""
    # TODO: GROUP BY category_id in DB
    return [
        {"category": "Pothole", "count": 35},
        {"category": "Street Light", "count": 28},
        {"category": "Garbage", "count": 22},
        {"category": "Water Leak", "count": 18},
    ]


@router.get("/complaints", response_model=List[ComplaintBrief])
def all_complaints(page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100)) -> list:
    """Paginated list of all complaints for admin review."""
    # TODO: paginate from DB
    return [{"id": 1, "title": "Sample complaint", "status": "submitted", "priority_level": "high", "category_name": "Pothole", "created_at": datetime.utcnow()}]
