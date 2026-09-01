# Complaint routing & crisis detection

`app/ml/classifier.py` turns complaint text (typed or transcribed) into:

| field | meaning |
|-------|---------|
| `category` | e.g. *Waterlogging / Flooding*, *Power Outage / Electricity* |
| `department` / `department_key` | the municipal department that should own it |
| `confidence` | 0–1, how strong the keyword evidence was |
| `matched_keywords` | which terms fired (for debugging / audit) |
| `is_crisis` / `crisis_type` / `crisis_department` | emergency detected → fast-track |
| `urgency` | `low` / `medium` / `high` / `critical` — feeds the priority engine |
| `urgency_signals` | words like "child", "hospital", "many days", "बच्चे" |
| `alternatives` | runner-up categories |

## How it decides

A curated **multilingual keyword map** (`CATEGORIES`). Civic vocabulary is small
and distinctive, so keyword rules beat an under-trained classifier here — and
they're debuggable (they tell you *why* they matched). Each category has
`strong` keywords (weight 3, near-unambiguous) and `weak` keywords (weight 1,
context). The matcher:

- works directly on **Devanagari / Tamil / Telugu / … script** and on Romanised
  "Hinglish" (`paani nahi aa raha`, `kachra`, `bijli gul`);
- whole-word matching for Latin terms, substring for Indic scripts;
- `confidence = 0.5·(top score / total score) + 0.5·min(1, top score / D)`.

### Vernacular confidence

The English keyword lists are larger than the vernacular ones, so an equally
decisive Hindi/Marathi/Tamil complaint scores fewer raw points. To stop that
from reading as "low confidence", when the complaint is vernacular (language is
Indic, or the text is >30% non-Latin script):

- the evidence divisor `D` drops from 6 → **4** (less absolute evidence needed);
- a category with **≥1 strong keyword hit** gets a **confidence floor of ~0.8**.

Result: a clear Marathi water-supply complaint now reports ~1.0 confidence
instead of ~0.6, matching how certain the routing actually is.

Languages currently covered in the keyword lists: **English, Hindi, Marathi**,
plus Romanised Hindi. Add more by extending the `strong` / `weak` lists — no
code change needed.

## Categories → departments

| Category | Department |
|----------|-----------|
| Waterlogging / Flooding | Storm Water Drainage Department |
| Blocked Drain / Sewage Overflow | Sewerage Board |
| Water Supply | Water Supply Department |
| Power Outage / Electricity | Electricity Board |
| Street Light | Street Lighting Department |
| Pothole / Road Damage | Public Works Department |
| Garbage / Sanitation | Solid Waste Management Department |
| Public Health / Mosquito | Public Health Department |
| Illegal Construction / Encroachment | Town Planning Department |
| Fallen Tree / Parks | Parks & Horticulture Department |
| Noise / Pollution | Pollution Control Board |
| Traffic Signal / Road Signage | Traffic Police |

Edit `DEPARTMENTS` and each category's `department` key to match your city's
actual org chart.

## Crisis detection

`CRISIS_RULES` scans for emergencies regardless of category:

| type | routed to |
|------|-----------|
| `fire`, `gas_leak`, `structure_collapse` | Fire & Emergency Services |
| `electrocution_hazard` | Electricity Board |
| `flooding_emergency` | Storm Water Drainage |
| `sewage_health_hazard` | Sewerage Board |
| `fallen_tree_blocking` | Parks & Horticulture |

When a crisis fires:

- `urgency` is forced to `critical`;
- if the civic-category evidence is thin (< ~2 strong hits) the complaint is
  **labelled and routed by the emergency itself** (e.g. "building me aag" →
  *Fire Emergency* → Fire & Emergency Services);
- the priority engine adds +0.25 to the score and records the reason.

## Where it runs

`_process_complaint_submission()` in `app/routes/complaints.py` calls
`route_complaint()` then `calculate_priority_score()` for **both** the text
(`POST /complaints/`) and voice (`POST /complaints/voice`) paths.

`POST /complaints/route-preview` runs just the router (no complaint created) —
used by the submit form's live "this will go to …" hint and for testing.

## Priority scoring

`app/ml/priority.py` combines: category urgency · crisis flag · urgency words ·
nearby open-complaint density (TODO: PostGIS query, currently 0) · SLA proximity
· age. Returns `(level, score, reasons[])` where `reasons` is shown to the
citizen and the officer.
