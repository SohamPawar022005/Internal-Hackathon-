"""
NIVARAN — FastAPI application entry point.

Responsibilities:
  • Create the FastAPI app instance
  • Configure CORS for frontend (localhost:5173)
  • Register all route modules under their prefixes
  • Create database tables on startup
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.routes import auth, complaints, officer, admin, geo

# ── App Instance ───────────────────────────────────────────────────────
app = FastAPI(
    title="NIVARAN API",
    description="AI-based Citizen Grievance Platform",
    version="0.1.0",
)

# ── CORS ───────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://frontend:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(complaints.router, prefix="/complaints", tags=["Complaints"])
app.include_router(officer.router, prefix="/officer", tags=["Officer"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(geo.router, prefix="/geo", tags=["Geo"])


# ── Startup ────────────────────────────────────────────────────────────
@app.on_event("startup")
def on_startup() -> None:
    """Create all tables if they don't exist yet."""
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        # DB may not be up yet — tables will be created on first successful connection
        import logging
        logging.warning(f"Could not create tables on startup (DB may be unavailable): {e}")


@app.get("/health")
def health_check() -> dict:
    """Simple liveness probe."""
    return {"status": "ok", "service": "nivaran-backend"}
