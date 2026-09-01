"""
Seed the database with complaints from data/seed_complaints.json.

Usage:
    python -m scripts.seed_database
"""

import json
from pathlib import Path
from app.database import SessionLocal, engine, Base
from app.models import Complaint, Department, Category, User


def seed() -> None:
    """Load seed_complaints.json into the database."""
    # TODO: create departments and categories first
    # TODO: create a default citizen user
    # TODO: read seed_complaints.json and insert Complaint rows
    # TODO: print summary of rows inserted
    data_path = Path(__file__).parent.parent / "data" / "seed_complaints.json"

    if not data_path.exists():
        print(f"Seed file not found: {data_path}")
        return

    with open(data_path) as f:
        complaints = json.load(f)

    print(f"Loaded {len(complaints)} complaints from seed file")

    # TODO: insert into DB using SessionLocal
    raise NotImplementedError


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    seed()
