"""Input sanitisation and PII redaction (Aadhaar, PAN, phone, bank account, email).

Every piece of free text is sanitised and redacted on the server before it reaches a
prompt, even though the browser redacts first.
"""

from __future__ import annotations

import re
import unicodedata

# Control chars, zero-width space and bidi overrides. ZWJ/ZWNJ (U+200C/D) are kept:
# Indic scripts need them to render conjuncts.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b\u200e\u200f\u202a-\u202e\u2066-\u2069]")

_INJECTION = re.compile(
    r"(ignore|disregard|forget|override)\s+(all\s+|any\s+|the\s+|your\s+)?"
    r"(previous|prior|above|earlier|system)?\s*(instructions?|prompts?|rules?|messages?)"
    r"|(reveal|show|print|repeat)\s+(your\s+|the\s+)?(system\s+prompt|hidden\s+instructions)"
    r"|you\s+are\s+now\s+",
    re.IGNORECASE,
)

# Order matters: more specific patterns run first.
_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("AADHAAR", re.compile(r"(?<!\d)[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}(?!\d)")),
    ("PHONE", re.compile(r"(?:\+91[\s-]?|(?<!\d))[6-9]\d{4}[\s-]?\d{5}(?!\d)")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE)),
    ("IFSC", re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b", re.IGNORECASE)),
    ("BANK_ACCOUNT", re.compile(r"(?<!\d)\d{9,18}(?!\d)")),
)


def redact_pii(text: str) -> str:
    """Mask identifiers with [LABEL] tokens."""
    for label, pattern in _PII_PATTERNS:
        text = pattern.sub(f"[{label}]", text)
    return text


def sanitize_text(text: str, max_chars: int) -> str:
    """Normalise, strip control characters, neutralise prompt delimiters and injection
    phrases, redact PII and cap length. Raises ValueError if nothing remains."""
    cleaned = unicodedata.normalize("NFKC", text)
    cleaned = _CONTROL_CHARS.sub("", cleaned)
    cleaned = cleaned.replace("<", "(").replace(">", ")")  # cannot forge <user_input> fences
    cleaned = _INJECTION.sub("[removed]", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    cleaned = redact_pii(cleaned)[:max_chars]
    if not cleaned:
        raise ValueError("empty text")
    return cleaned
