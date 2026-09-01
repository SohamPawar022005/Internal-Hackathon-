"""
Complaint router — text → category → department, with crisis detection.

Given a complaint (typed, or transcribed from voice), decide:

  • which **category** it belongs to (Waterlogging, Power Outage, …),
  • which municipal **department** should own it,
  • whether it describes a **crisis / emergency** that must jump the queue,
  • a rough **urgency** hint the priority engine can use.

Why keyword rules and not a trained model
─────────────────────────────────────────
Civic-complaint vocabulary is small and highly distinctive ("transformer",
"pothole", "sewage", "गड्ढा", "खड्डा", "बिजली"), and we have no labelled
training data yet.  A curated multilingual keyword map is more accurate
here than an under-trained classifier, is debuggable (it tells you *which*
words matched), and needs no model download.  `CATEGORIES` below is meant
to be extended — add languages / synonyms freely.

The matcher is script-aware: it works directly on Devanagari / Tamil /
etc. text, and also on Romanised "Hinglish" ("paani nahi aa raha",
"kachra", "bijli gul").  For best results the caller passes the language
code the ASR/typing pipeline detected, but it is optional.

Public API
──────────
  route_complaint(text, language=None) -> RouteResult (dict)
  classify(text) -> (category_name, confidence)      # back-compat shim
  list_categories() -> list[dict]
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional, Tuple

# ── Department catalogue ───────────────────────────────────────────────
# Names follow common Indian urban-local-body / parastatal naming.  Adjust
# to match your city's actual org chart.
DEPARTMENTS = {
    "pwd": "Public Works Department",
    "water": "Water Supply Department",
    "drainage": "Storm Water Drainage Department",
    "sewerage": "Sewerage Board",
    "electricity": "Electricity Board",
    "streetlight": "Street Lighting Department",
    "sanitation": "Solid Waste Management Department",
    "health": "Public Health Department",
    "planning": "Town Planning Department",
    "horticulture": "Parks & Horticulture Department",
    "pollution": "Pollution Control Board",
    "traffic": "Traffic Police",
    "fire": "Fire & Emergency Services",
    "animal": "Veterinary & Animal Control Department",
    "grievance": "Public Grievance Cell",
}

# ── Category rules ─────────────────────────────────────────────────────
# Each category: department + weighted keyword lists.  "strong" keywords
# are near-unambiguous (weight 3); "weak" keywords are supporting context
# (weight 1).  Keywords are matched case-insensitively as whole words
# where the term is Latin/short, or as substrings for Indic scripts.
CATEGORIES: list[dict] = [
    {
        "name": "Waterlogging / Flooding",
        "department": "drainage",
        "urgency": "high",
        "strong": [
            "waterlogging", "water logging", "water logged", "flooded",
            "flooding", "flood", "knee deep water", "rain water accumulation",
            "जलभराव", "पानी भर", "पानी जमा", "जलजमाव", "बाढ़", "बारिश का पानी",
            "पाणी साच", "पाणी तुंब", "पूर", "साचले", "तुंबले",
            "paani bhar", "paani jama", "jal bharav",
        ],
        "weak": ["rain", "monsoon", "drain overflow", "बारिश", "नाला", "पाऊस"],
    },
    {
        "name": "Blocked Drain / Sewage Overflow",
        "department": "sewerage",
        "urgency": "high",
        "strong": [
            "sewage", "sewer", "sewage overflow", "drain blocked",
            "blocked drain", "choked drain", "manhole", "open manhole",
            "gutter overflow", "dirty water flowing", "foul smell drain",
            "नाली जाम", "सीवर", "सीवेज", "मैनहोल", "गटर", "गंदा पानी बह",
            "गटार तुंबले", "गटार", "सांडपाणी", "मैला",
            "nali jam", "gutter jam", "sewer overflow",
        ],
        "weak": ["smell", "stink", "बदबू", "दुर्गंध", "घाण", "वास"],
    },
    {
        "name": "Water Supply",
        "department": "water",
        "urgency": "high",
        "strong": [
            "no water", "water supply", "no water supply", "water shortage",
            "low pressure water", "dirty water supply", "contaminated water",
            "muddy water", "pipeline leak", "pipe burst", "water pipe leak",
            "tap dry", "no tap water", "water tanker",
            "पानी नहीं आ", "पानी नहीं आया", "पानी की सप्लाई", "पानी की कमी",
            "गंदा पानी आ", "पाइपलाइन लीक", "पाइप फट", "नल सूख",
            "पाणी येत नाही", "पाणीपुरवठा", "पाणी येत नाहीये", "नळाला पाणी नाही",
            "पाइप फुट", "गढूळ पाणी",
            "paani nahi aa", "paani nahi", "pani nahi", "nal me pani nahi",
            "water nahi aa raha",
        ],
        "weak": ["tap", "nal", "नल", "नळ", "boring", "borewell", "बोरिंग"],
    },
    {
        "name": "Power Outage / Electricity",
        "department": "electricity",
        "urgency": "high",
        "strong": [
            "power cut", "power outage", "no electricity", "no power",
            "power failure", "load shedding", "transformer", "transformer blast",
            "transformer spark", "electric pole", "loose wire", "hanging wire",
            "live wire", "current in", "electric shock", "short circuit",
            "meter burnt", "voltage fluctuation", "frequent tripping",
            "बिजली नहीं", "बिजली गुल", "बिजली कट", "लाइट नहीं आ", "ट्रांसफार्मर",
            "बिजली का खंभा", "तार लटक", "करंट आ", "शॉर्ट सर्किट", "वोल्टेज",
            "वीज नाही", "वीज गेली", "वीजपुरवठा खंडित", "रोहित्र", "डीपी",
            "तार तुटला", "विजेचा धक्का",
            "bijli nahi", "bijli gul", "light nahi aa", "current aa raha",
            "power nahi",
        ],
        "weak": ["light", "electricity", "meter", "मीटर", "लाइट", "वीज", "दिवा"],
    },
    {
        "name": "Street Light",
        "department": "streetlight",
        "urgency": "medium",
        "strong": [
            "street light", "streetlight", "street lamp", "road light",
            "pole light not working", "dark street", "light not glowing",
            "स्ट्रीट लाइट", "सड़क की बत्ती", "खंभे की लाइट", "रोड लाइट",
            "अंधेरा रहता", "लाइट खराब",
            "पथदिवा", "रस्त्यावरचा दिवा", "स्ट्रीट लाईट बंद", "अंधार",
            "street light band", "road light kharab",
        ],
        "weak": ["light", "lamp", "pole", "दिवा", "बत्ती", "खांब"],
    },
    {
        "name": "Pothole / Road Damage",
        "department": "pwd",
        "urgency": "medium",
        "strong": [
            "pothole", "pot hole", "potholes", "broken road", "damaged road",
            "road caved", "road cave in", "crater", "uneven road", "road dug",
            "road not repaired", "bad road condition", "cracks on road",
            "गड्ढा", "गड्ढे", "सड़क टूट", "सड़क खराब", "सड़क धंस", "सड़क खुदी",
            "खड्डा", "खड्डे", "रस्ता खराब", "रस्ता तुटला", "रस्त्यावर खड्डे",
            "gaddha", "gadde", "sadak kharab", "sadak toot", "road me gaddha",
            "khadda", "khadde",
        ],
        "weak": ["road", "street", "highway", "सड़क", "रस्ता", "गली"],
    },
    {
        "name": "Garbage / Sanitation",
        "department": "sanitation",
        "urgency": "medium",
        "strong": [
            "garbage", "trash", "waste not collected", "garbage not picked",
            "overflowing bin", "garbage dump", "rubbish", "litter", "dumping",
            "dead animal", "debris not cleared", "no sweeping", "garbage pile",
            "कचरा", "कूड़ा", "कचरा फैला", "डस्टबिन भर", "गंदगी", "कूड़ेदान",
            "कचरा उचल", "कचरा साचला", "कचरापेटी", "कचरा उठला नाही",
            "kachra", "kachara", "kacra", "kuda", "kooda", "kachraa",
        ],
        "weak": [
            "clean", "sweep", "bin", "dustbin", "uthaya", "utha nahi",
            "सफाई", "स्वच्छता", "झाडू", "घाण", "उठा",
        ],
    },
    {
        "name": "Public Health / Mosquito",
        "department": "health",
        "urgency": "medium",
        "strong": [
            "mosquito", "mosquito breeding", "dengue", "malaria", "chikungunya",
            "fogging not done", "stagnant water mosquito", "spread of disease",
            "epidemic", "food poisoning", "unhygienic",
            "मच्छर", "डेंगू", "मलेरिया", "फॉगिंग", "बीमारी फैल", "महामारी",
            "डास", "डेंग्यू", "साथीचा आजार", "धूर फवारणी",
            "machhar", "dengue", "fogging nahi",
        ],
        "weak": ["health", "disease", "fever", "बीमारी", "बुखार", "आजार", "ताप"],
    },
    {
        "name": "Illegal Construction / Encroachment",
        "department": "planning",
        "urgency": "low",
        "strong": [
            "illegal construction", "unauthorized construction", "encroachment",
            "footpath encroachment", "illegal building", "no permission building",
            "illegal hawker", "shop on footpath", "extension without sanction",
            "अवैध निर्माण", "अतिक्रमण", "बिना अनुमति निर्माण", "फुटपाथ पर कब्जा",
            "अनधिकृत बांधकाम", "अतिक्रमण", "फूटपाथवर अतिक्रमण",
            "avaidh nirman", "atikraman",
        ],
        "weak": ["construction", "building", "footpath", "निर्माण", "बांधकाम"],
    },
    {
        "name": "Fallen Tree / Parks",
        "department": "horticulture",
        "urgency": "medium",
        "strong": [
            "tree fallen", "tree fell", "fallen branch", "dangerous tree",
            "tree uprooted", "dry tree", "tree about to fall", "park not maintained",
            "garden broken", "playground damaged",
            "पेड़ गिर", "पेड़ टूट", "डाल गिर", "सूखा पेड़", "पार्क खराब",
            "झाड पडले", "झाड कोसळले", "फांदी तुटली", "उद्यान", "बाग",
            "ped gir", "jhaad pada",
        ],
        "weak": ["tree", "park", "garden", "पेड़", "झाड", "उद्यान", "बाग"],
    },
    {
        "name": "Noise / Pollution",
        "department": "pollution",
        "urgency": "low",
        "strong": [
            "noise pollution", "loud music", "loudspeaker", "loud dj",
            "air pollution", "smoke from factory", "burning garbage smoke",
            "industrial pollution", "bad air quality",
            "शोर", "ध्वनि प्रदूषण", "लाउडस्पीकर", "तेज आवाज", "धुआं", "वायु प्रदूषण",
            "आवाज", "ध्वनी प्रदूषण", "कर्कश आवाज", "धूर", "हवा प्रदूषण",
            "shor", "loud music", "awaaz",
        ],
        "weak": ["noise", "smoke", "pollution", "प्रदूषण", "धुआं", "प्रदूषण"],
    },
    {
        "name": "Traffic Signal / Road Signage",
        "department": "traffic",
        "urgency": "medium",
        "strong": [
            "traffic signal not working", "traffic light broken", "signal off",
            "zebra crossing faded", "road sign missing", "no traffic light",
            "signal timing wrong",
            "ट्रैफिक सिग्नल", "सिग्नल खराब", "सिग्नल बंद", "ज़ेबरा क्रॉसिंग",
            "वाहतूक सिग्नल", "सिग्नल बंद आहे",
            "signal kharab", "signal band",
        ],
        "weak": ["signal", "traffic", "crossing", "सिग्नल", "ट्रैफिक", "वाहतूक"],
    },
]

# ── Crisis / emergency detection ──────────────────────────────────────
# If any of these match, the complaint is flagged as a crisis regardless
# of category, priority is bumped, and (where relevant) the Fire &
# Emergency department is co-notified.
CRISIS_RULES: list[dict] = [
    {
        "type": "fire",
        "department": "fire",
        "keywords": [
            "fire", "on fire", "flames", "building burning", "blaze",
            "आग लग", "आग लगी", "आग", "जल रहा", "धू धू",
            "आग लागली", "जळत", "भडका",
            "aag lag", "aag lagi", "building me aag",
        ],
    },
    {
        "type": "gas_leak",
        "department": "fire",
        "keywords": [
            "gas leak", "gas leakage", "smell of gas", "lpg leak", "cylinder leak",
            "गैस लीक", "गैस रिसाव", "गैस की गंध",
            "गॅस गळती", "गॅस वास",
            "gas leak ho raha", "gas ki badbu",
        ],
    },
    {
        "type": "structure_collapse",
        "department": "fire",
        "keywords": [
            "building collapse", "wall collapse", "slab collapsed", "house collapsed",
            "roof caved", "bridge collapse", "under debris", "people trapped",
            "इमारत गिर", "दीवार गिर", "छत गिर", "मलबे में दब", "पुल गिर",
            "इमारत कोसळली", "भिंत पडली", "स्लॅब कोसळला", "ढिगाऱ्याखाली",
            "building gir gayi", "deewar gir",
        ],
    },
    {
        "type": "electrocution_hazard",
        "department": "electricity",
        "keywords": [
            "live wire", "current in water", "electric shock", "electrocuted",
            "sparking wire", "wire in water", "pole sparking", "shock lag",
            "करंट आ रहा", "तार में करंट", "पानी में करंट", "चिंगारी", "बिजली का झटका",
            "विजेचा धक्का", "तारेत करंट", "पाण्यात करंट", "ठिणग्या",
            "current aa raha", "taar me current", "bijli ka jhatka",
        ],
    },
    {
        "type": "flooding_emergency",
        "department": "drainage",
        "keywords": [
            "water entering house", "house flooded", "society flooded",
            "car submerged", "people stuck in water", "rescue needed",
            "घर में पानी घुस", "घर डूब", "पानी में फंस", "बचाओ",
            "घरात पाणी शिरले", "पाण्यात अडकले", "वाचवा",
            "ghar me paani ghus", "paani ghar me",
        ],
    },
    {
        "type": "sewage_health_hazard",
        "department": "sewerage",
        "keywords": [
            "sewage entering homes", "drinking water contaminated with sewage",
            "cholera", "outbreak",
            "पीने के पानी में सीवेज", "हैजा", "बीमारी फैल रही",
            "पिण्याच्या पाण्यात सांडपाणी", "साथ पसरली",
        ],
    },
    {
        "type": "fallen_tree_blocking",
        "department": "horticulture",
        "keywords": [
            "tree fell on car", "tree blocking road", "tree on wires",
            "tree fell on house", "person under tree",
            "पेड़ गाड़ी पर गिर", "पेड़ से रास्ता बंद", "पेड़ तार पर गिर",
            "झाड अंगावर पडले", "झाडाने रस्ता बंद", "झाड गाडीवर पडले",
        ],
    },
]

_CRISIS_URGENCY = "critical"

# When a crisis is detected but the civic-category signal is weak, the
# complaint is labelled by the emergency itself.
_CRISIS_CATEGORY = {
    "fire": "Fire Emergency",
    "gas_leak": "Gas Leak Emergency",
    "structure_collapse": "Building / Structure Collapse",
    "electrocution_hazard": "Electrical Hazard",
    "flooding_emergency": "Flooding Emergency",
    "sewage_health_hazard": "Sewage Health Hazard",
    "fallen_tree_blocking": "Fallen Tree Blocking Road",
}

# Words that intensify urgency without being a full crisis.
_URGENCY_BOOSTERS = [
    "urgent", "emergency", "immediately", "danger", "dangerous", "risk to life",
    "child", "children", "elderly", "hospital", "school", "accident",
    "many days", "several days", "one week", "whole area", "entire colony",
    "तुरंत", "आपातकाल", "खतरा", "जानलेवा", "बच्चे", "अस्पताल", "कई दिन",
    "पूरा इलाका", "दुर्घटना",
    "तातडीने", "आणीबाणी", "धोका", "जीवितहानी", "लहान मुले", "रुग्णालय",
    "अनेक दिवस", "संपूर्ण परिसर", "अपघात",
]


# ── Matching engine ───────────────────────────────────────────────────
def _normalize(text: str) -> str:
    """Lowercase, NFC-normalize, collapse whitespace. Keeps Indic scripts."""
    text = unicodedata.normalize("NFC", text or "")
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return f" {text} "


_LATIN_KW = re.compile(r"^[a-z0-9 '\-]+$")


def _kw_hits(norm_text: str, keyword: str) -> int:
    kw = keyword.lower().strip()
    if not kw:
        return 0
    if _LATIN_KW.match(kw):
        # whole-word / phrase match for Latin keywords
        pattern = r"(?<![a-z])" + re.escape(kw) + r"(?![a-z])"
        return len(re.findall(pattern, norm_text))
    # substring match for Indic scripts (word boundaries are unreliable)
    return norm_text.count(kw)


def _score_categories(norm_text: str) -> list[dict]:
    scored = []
    for cat in CATEGORIES:
        matched: list[str] = []
        score = 0.0
        strong_hits = 0
        for kw in cat["strong"]:
            h = _kw_hits(norm_text, kw)
            if h:
                score += 3.0 * h
                strong_hits += h
                matched.append(kw)
        for kw in cat["weak"]:
            h = _kw_hits(norm_text, kw)
            if h:
                score += 1.0 * h
                matched.append(kw)
        if score > 0:
            scored.append({
                "name": cat["name"],
                "department": cat["department"],
                "urgency": cat["urgency"],
                "score": round(score, 2),
                "strong_hits": strong_hits,
                "matched": matched,
            })
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored


_NON_LATIN = re.compile(r"[^\x00-\x7f]")


def _is_vernacular(text: str, language: Optional[str]) -> bool:
    """True when the complaint is in an Indian vernacular language.

    Either the pipeline told us so, or the text is written in a non-Latin
    (Indic) script.
    """
    from app.ml.language import is_indic

    if is_indic(language):
        return True
    letters = [c for c in text if c.isalpha()]
    if letters and sum(1 for c in letters if _NON_LATIN.match(c)) / len(letters) > 0.3:
        return True
    return False


def _detect_crisis(norm_text: str) -> Optional[dict]:
    for rule in CRISIS_RULES:
        hits = [kw for kw in rule["keywords"] if _kw_hits(norm_text, kw)]
        if hits:
            return {
                "type": rule["type"],
                "department": rule["department"],
                "matched": hits,
            }
    return None


def _urgency_boost(norm_text: str) -> list[str]:
    return [w for w in _URGENCY_BOOSTERS if _kw_hits(norm_text, w)]


_URGENCY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_URGENCY_NAME = {v: k for k, v in _URGENCY_RANK.items()}


def route_complaint(text: str, language: Optional[str] = None) -> dict:
    """Route a complaint to a category + department, flagging emergencies.

    Args:
        text: complaint text (typed or transcribed).  Title + description
              concatenated is fine.
        language: optional bare ISO code from the ASR / typing pipeline.
              Currently informational (the matcher is script-driven), but
              recorded in the result for auditing.

    Returns a dict:
      {
        "category": str,
        "department": str,           # human-readable department name
        "department_key": str,
        "confidence": float,         # 0..1
        "matched_keywords": [str],
        "is_crisis": bool,
        "crisis_type": str | None,
        "crisis_department": str | None,
        "urgency": "low|medium|high|critical",
        "urgency_signals": [str],
        "alternatives": [{"category", "department", "score"}],
        "language": str | None,
      }
    """
    norm = _normalize(text)
    scored = _score_categories(norm)
    crisis = _detect_crisis(norm)
    boosters = _urgency_boost(norm)

    vernacular = _is_vernacular(text, language)

    top_score = scored[0]["score"] if scored else 0.0
    if scored:
        top = scored[0]
        total = sum(c["score"] for c in scored)
        # confidence: share of total score, tempered by absolute evidence.
        share = top["score"] / total if total else 0.0
        # The vernacular keyword lists are sparser than the English ones —
        # a strong hit in Hindi/Marathi/Tamil is just as decisive but
        # scores fewer points, so we need less absolute evidence to be
        # confident and we put a floor under a clear strong match.
        evidence_div = 4.0 if vernacular else 6.0
        evidence = min(1.0, top["score"] / evidence_div)
        confidence = round(0.5 * share + 0.5 * evidence, 3)
        if vernacular and top.get("strong_hits", 0) >= 1:
            confidence = round(max(confidence, 0.75) + 0.05, 3)
            confidence = min(confidence, 1.0)
        category = top["name"]
        dept_key = top["department"]
        urgency_rank = _URGENCY_RANK[top["urgency"]]
    else:
        category = "General / Unclassified"
        dept_key = "grievance"
        confidence = 0.0
        urgency_rank = _URGENCY_RANK["low"]

    # Crisis overrides urgency and can redirect the owning department.
    if crisis:
        urgency_rank = _URGENCY_RANK["critical"]
        # If the civic-category evidence is thin (< ~2 strong keyword
        # hits), label and route the complaint by the emergency itself.
        if top_score < 6.0:
            category = _CRISIS_CATEGORY.get(crisis["type"], category)
            dept_key = crisis["department"]
            confidence = max(confidence, 0.9)
    elif boosters:
        urgency_rank = min(3, urgency_rank + 1)

    matched_keywords = scored[0]["matched"] if scored else []
    if crisis:
        matched_keywords = list(dict.fromkeys(matched_keywords + crisis["matched"]))

    return {
        "category": category,
        "department": DEPARTMENTS[dept_key],
        "department_key": dept_key,
        "confidence": confidence,
        "matched_keywords": matched_keywords,
        "is_crisis": bool(crisis),
        "crisis_type": crisis["type"] if crisis else None,
        "crisis_department": DEPARTMENTS[crisis["department"]] if crisis else None,
        "urgency": _URGENCY_NAME[urgency_rank],
        "urgency_signals": boosters,
        "alternatives": [
            {"category": c["name"], "department": DEPARTMENTS[c["department"]],
             "score": c["score"]}
            for c in scored[1:4]
        ],
        "language": language,
    }


# ── Back-compat shims ─────────────────────────────────────────────────
def classify(text: str) -> Tuple[str, float]:
    """Legacy interface: return (category_name, confidence)."""
    r = route_complaint(text)
    return r["category"], r["confidence"]


def list_categories() -> list[dict]:
    """All routable categories and their departments (for admin UI / docs)."""
    return [
        {"name": c["name"], "department": DEPARTMENTS[c["department"]],
         "default_urgency": c["urgency"]}
        for c in CATEGORIES
    ]


def train_classifier(texts: list[str], labels: list[str]) -> None:  # noqa: ARG001
    """No-op: the router is rule-based. Kept so callers don't break."""
    return None
