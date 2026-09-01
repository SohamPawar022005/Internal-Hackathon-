"""
Generate ~150-200 synthetic seed complaints across 8 categories.

Categories: Pothole, Street Light, Garbage, Water Leak, Sewage,
            Road Damage, Noise, Illegal Construction

Output: data/seed_complaints.json
"""

import json
import random
from pathlib import Path


def generate_complaints(count: int = 175) -> list[dict]:
    """Generate synthetic complaint records.

    Each record should include:
      - title, description, category
      - location_lat, location_lng, address, ward
      - status (mostly 'submitted', some 'resolved')
      - language ('en' or 'hi')

    Returns:
        List of complaint dicts ready for DB seeding.
    """
    # TODO: create realistic titles/descriptions per category
    # TODO: scatter lat/lng across Delhi NCR bounding box
    # TODO: randomize status distribution (70% submitted, 20% in_progress, 10% resolved)
    raise NotImplementedError


if __name__ == "__main__":
    complaints = generate_complaints()
    out_path = Path(__file__).parent.parent / "data" / "seed_complaints.json"
    out_path.write_text(json.dumps(complaints, indent=2, default=str))
    print(f"Wrote {len(complaints)} complaints to {out_path}")
