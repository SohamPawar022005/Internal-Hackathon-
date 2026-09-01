"""
Auth routes — fake login (role selector) and current-user endpoint.

No real authentication; this just lets the frontend pick citizen / officer / admin
and receive a mock user object back.
"""

from fastapi import APIRouter
from app.schemas import LoginRequest, UserOut

router = APIRouter()


@router.post("/login", response_model=UserOut)
def fake_login(payload: LoginRequest) -> dict:
    """Return a mock user for the chosen role — no password required."""
    # TODO: replace with real auth (JWT or session) after hackathon
    return {
        "id": 1,
        "name": payload.name,
        "email": f"{payload.name.lower().replace(' ', '.')}@nivaran.dev",
        "role": payload.role,
        "department_id": 1 if payload.role == "officer" else None,
    }


@router.get("/me", response_model=UserOut)
def get_current_user() -> dict:
    """Return the currently logged-in user."""
    # TODO: extract user from auth header / session
    return {
        "id": 1,
        "name": "Test User",
        "email": "test@nivaran.dev",
        "role": "citizen",
        "department_id": None,
    }
