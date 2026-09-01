"""
SQLAlchemy ORM models for NIVARAN.

╔══════════════════════════════════════════════════════════════════════╗
║  TABLE FIELD REFERENCE (from PRD)                                  ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  User                                                              ║
║    id, name, email, phone, role (citizen|officer|admin),            ║
║    department_id (FK, nullable), created_at                        ║
║                                                                    ║
║  Department                                                        ║
║    id, name, description, sla_days                                 ║
║                                                                    ║
║  Category                                                          ║
║    id, name, description, department_id (FK), keywords (text[])    ║
║                                                                    ║
║  Complaint                                                         ║
║    id, title, description, category_id (FK), department_id (FK),   ║
║    user_id (FK), status (submitted|assigned|in_progress|resolved   ║
║    |rejected), priority_level (critical|high|medium|low),          ║
║    priority_score (float), priority_reasons (text[]),              ║
║    location_lat, location_lng, address, ward,                      ║
║    embedding (float[]), language, created_at, updated_at,          ║
║    resolved_at, sla_deadline                                       ║
║                                                                    ║
║  Attachment                                                        ║
║    id, complaint_id (FK), file_url, file_type, uploaded_at         ║
║                                                                    ║
║  ComplaintUpdate                                                   ║
║    id, complaint_id (FK), status, comment, updated_by (FK),        ║
║    created_at                                                      ║
║                                                                    ║
║  SimilarComplaint                                                  ║
║    id, complaint_id (FK), similar_complaint_id (FK),               ║
║    similarity_score (float)                                        ║
║                                                                    ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, ForeignKey, Enum, ARRAY,
    Boolean,
)
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    """Platform user — citizen, officer, or admin."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    phone = Column(String(20), nullable=True)
    role = Column(
        Enum("citizen", "officer", "admin", name="user_role"),
        default="citizen",
        nullable=False,
    )
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # TODO: add relationships (complaints, department)


class Department(Base):
    """A municipal department responsible for a class of complaints."""
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    sla_days = Column(Integer, default=7)

    # TODO: add relationships (categories, officers)


class Category(Base):
    """Complaint category (e.g., Pothole, Street Light, Garbage)."""
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    keywords = Column(ARRAY(String), default=[])

    # TODO: add relationship to department


class Complaint(Base):
    """Core entity — a citizen grievance report."""
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(
        Enum("submitted", "assigned", "in_progress", "resolved", "rejected",
             name="complaint_status"),
        default="submitted",
        nullable=False,
    )
    priority_level = Column(
        Enum("critical", "high", "medium", "low", name="priority_level"),
        default="medium",
        nullable=True,
    )
    priority_score = Column(Float, nullable=True)
    priority_reasons = Column(ARRAY(String), default=[])
    location_lat = Column(Float, nullable=True)
    location_lng = Column(Float, nullable=True)
    address = Column(Text, nullable=True)
    ward = Column(String(50), nullable=True)
    embedding = Column(ARRAY(Float), nullable=True)
    language = Column(String(10), default="en")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    sla_deadline = Column(DateTime, nullable=True)

    # TODO: add relationships (user, category, department, attachments, updates, similar)


class Attachment(Base):
    """File attached to a complaint (image, PDF, etc.)."""
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    complaint_id = Column(Integer, ForeignKey("complaints.id"), nullable=False)
    file_url = Column(String(500), nullable=False)
    file_type = Column(String(50), nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    # TODO: add relationship to complaint


class ComplaintUpdate(Base):
    """Timeline entry — status change or officer comment on a complaint."""
    __tablename__ = "complaint_updates"

    id = Column(Integer, primary_key=True, index=True)
    complaint_id = Column(Integer, ForeignKey("complaints.id"), nullable=False)
    status = Column(String(30), nullable=True)
    comment = Column(Text, nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # TODO: add relationships (complaint, user)


class SimilarComplaint(Base):
    """Pair-wise link between complaints the ML pipeline considers similar."""
    __tablename__ = "similar_complaints"

    id = Column(Integer, primary_key=True, index=True)
    complaint_id = Column(Integer, ForeignKey("complaints.id"), nullable=False)
    similar_complaint_id = Column(Integer, ForeignKey("complaints.id"), nullable=False)
    similarity_score = Column(Float, nullable=False)

    # TODO: add relationships
