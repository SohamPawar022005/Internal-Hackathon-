"""
Text translation — vernacular complaint text → English (and back).

Used to show the citizen their transcript in *both* the language they
spoke and an English rendering ("We heard … / In English …"), and to give
officers who don't read the language an understandable copy.

Backends, tried in order (all best-effort — every failure returns None so
the caller can just skip the second line):

  1. Sarvam  /translate  (mayura:v1 / sarvam-translate:v1)  — needs SARVAM_API_KEY
  2. deep-translator's GoogleTranslator                     — needs `deep-translator`
  3. give up → None

Public API:
  • translate_text(text, source_language=None, target="en") -> str | None
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import requests
from dotenv import load_dotenv

from app.ml.language import bare_code, to_regional_code

load_dotenv()

logger = logging.getLogger(__name__)

SARVAM_API_KEY: Optional[str] = os.getenv("SARVAM_API_KEY") or None
SARVAM_TRANSLATE_URL = "https://api.sarvam.ai/translate"
SARVAM_TRANSLATE_MODEL = os.getenv("SARVAM_TRANSLATE_MODEL", "sarvam-translate:v1")
HTTP_TIMEOUT = int(os.getenv("VOICE_HTTP_TIMEOUT", "30"))

# mayura:v1 caps at 1000 chars, sarvam-translate:v1 at 2000.
_MAX_CHARS = 1900


def _same_language(source: Optional[str], target: str) -> bool:
    s = bare_code(source)
    return s is not None and s == bare_code(target)


def _translate_sarvam(text: str, source: Optional[str], target: str) -> Optional[str]:
    if not SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY not set")
    # sarvam-translate:v1 needs an explicit source; mayura:v1 accepts "auto".
    if source:
        src = to_regional_code(source)
        model = SARVAM_TRANSLATE_MODEL
    else:
        src = "auto"
        model = "mayura:v1"
    payload = {
        "input": text[:_MAX_CHARS],
        "source_language_code": src,
        "target_language_code": to_regional_code(target),
        "model": model,
        "mode": "formal",
    }
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json",
    }
    resp = requests.post(
        SARVAM_TRANSLATE_URL, json=payload, headers=headers, timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    out = (resp.json().get("translated_text") or "").strip()
    if not out:
        raise RuntimeError("Sarvam translate returned empty text")
    return out


def _translate_google(text: str, source: Optional[str], target: str) -> Optional[str]:
    from deep_translator import GoogleTranslator  # noqa: PLC0415

    src = bare_code(source) or "auto"
    out = GoogleTranslator(source=src, target=bare_code(target) or "en").translate(
        text[:4900]
    )
    out = (out or "").strip()
    if not out:
        raise RuntimeError("GoogleTranslator returned empty text")
    return out


def translate_text(
    text: str,
    source_language: Optional[str] = None,
    target: str = "en",
) -> Optional[str]:
    """Translate ``text`` into ``target`` (default English).

    Returns the translation, or ``None`` if translation isn't needed
    (text is already in the target language) or every backend failed.
    """
    text = (text or "").strip()
    if not text:
        return None
    if _same_language(source_language, target):
        return None

    for name, fn in (("sarvam", _translate_sarvam), ("google", _translate_google)):
        try:
            out = fn(text, source_language, target)
            if out and out.strip().lower() != text.strip().lower():
                logger.info("Translation ok via %s (%d chars)", name, len(out))
                return out
        except Exception as e:  # noqa: BLE001 - best effort, try next
            logger.warning("Translation backend %s failed: %s", name, e)

    return None
