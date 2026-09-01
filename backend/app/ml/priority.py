"""
Priority scoring engine.

Turns a routed complaint into a priority *level* + numeric *score* + the
human-readable *reasons* behind it, so officers see why something is
flagged and citizens get an honest ETA.

Signals combined (each capped, then summed and clamped to [0, 1]):
  • category urgency        — from the router (low / medium / high / critical)
  • crisis flag             — emergency detected in the text
  • explicit urgency words  — "child", "hospital", "many days", "बच्चे" …
  • cluster density         — how many open complaints are nearby
  • SLA proximity           — approaching or past the resolution deadline
  • age                     — how long it has sat unresolved
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

_URGENCY_BASE = {"low": 0.20, "medium": 0.42, "high": 0.62, "critical": 0.88}

_LEVEL_THRESHOLDS = [
    (0.80, "critical"),
    (0.58, "high"),
    (0.34, "medium"),
    (0.0, "low"),
]


def _as_datetime(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _level_for(score: float) -> str:
    for threshold, level in _LEVEL_THRESHOLDS:
        if score >= threshold:
            return level
    return "low"


def calculate_priority_score(
    complaint: dict,
    nearby_open_count: int = 0,
) -> Tuple[str, float, List[str]]:
    """Compute priority for a complaint.

    Args:
        complaint: dict that may contain:
            urgency          "low" | "medium" | "high" | "critical"  (from router)
            is_crisis        bool
            urgency_signals  list[str]
            category         str  (for the reason text)
            created_at       datetime | ISO str
            sla_deadline     datetime | ISO str
            status           str
        nearby_open_count: number of open complaints within a small radius.

    Returns:
        (level, score, reasons)
    """
    reasons: List[str] = []
    score = 0.0

    # ── Category urgency ─────────────────────────────────────────────
    urgency = (complaint.get("urgency") or "medium").lower()
    base = _URGENCY_BASE.get(urgency, 0.42)
    score += base
    category = complaint.get("category") or "complaint"
    reasons.append(f"{category} is a {urgency}-urgency category")

    # ── Crisis ──────────────────────────────────────────────────────
    if complaint.get("is_crisis"):
        score += 0.25
        crisis_type = (complaint.get("crisis_type") or "emergency").replace("_", " ")
        reasons.append(f"Emergency detected in the report ({crisis_type})")

    # ── Explicit urgency words ──────────────────────────────────────
    signals = complaint.get("urgency_signals") or []
    if signals:
        bump = min(0.15, 0.05 * len(signals))
        score += bump
        preview = ", ".join(signals[:3])
        reasons.append(f"Urgency wording in the report: {preview}")

    # ── Cluster density ─────────────────────────────────────────────
    if nearby_open_count > 0:
        bump = min(0.20, 0.03 * nearby_open_count)
        score += bump
        reasons.append(
            f"{nearby_open_count} other open complaint(s) reported nearby"
        )

    # ── SLA proximity ───────────────────────────────────────────────
    now = datetime.utcnow()
    sla = _as_datetime(complaint.get("sla_deadline"))
    status = (complaint.get("status") or "").lower()
    if sla and status not in ("resolved", "rejected"):
        hours_left = (sla - now).total_seconds() / 3600
        if hours_left < 0:
            score += 0.20
            reasons.append("SLA deadline has already passed")
        elif hours_left < 24:
            score += 0.10
            reasons.append("SLA deadline is within 24 hours")

    # ── Age ─────────────────────────────────────────────────────────
    created = _as_datetime(complaint.get("created_at"))
    if created and status not in ("resolved", "rejected"):
        age_days = (now - created).total_seconds() / 86400
        if age_days >= 7:
            score += 0.12
            reasons.append(f"Unresolved for {int(age_days)} days")
        elif age_days >= 3:
            score += 0.06
            reasons.append(f"Unresolved for {int(age_days)} days")

    score = round(max(0.0, min(1.0, score)), 3)
    return _level_for(score), score, reasons
