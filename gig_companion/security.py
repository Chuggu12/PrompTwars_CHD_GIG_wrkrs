"""Input sanitisation, PII redaction and privacy-safe logging.

Rules enforced here:
  * Every piece of user text is sanitised before it reaches a prompt.
  * Aadhaar, phone, email, PAN, IFSC and bank-account numbers are masked
    before any text is sent to the LLM.
  * Loggers obtained via `get_logger` redact PII from every record, and the
    app never logs raw user text in the first place.
"""

from __future__ import annotations

import logging
import re
import unicodedata

# Control chars, zero-width space and bidi overrides. ZWJ/ZWNJ (U+200C/D) are kept:
# Indic scripts need them to render conjuncts correctly.
_CONTROL_CHARS = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​\u200E\u200F\u202A-\u202E\u2066-\u2069]"
)

_INJECTION_PATTERN = re.compile(
    r"(ignore|disregard|forget|override)\s+(all\s+|any\s+|the\s+)?"
    r"(previous|prior|above|earlier|system)\s+(instructions?|prompts?|rules?|messages?)"
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


def sanitize_user_text(text: str, max_chars: int = 1500) -> str:
    """Normalise and neutralise untrusted text before it is used in a prompt.

    Raises:
        ValueError: if nothing meaningful remains after cleaning.
    """
    if not isinstance(text, str):
        raise TypeError("Expected text input.")
    cleaned = unicodedata.normalize("NFKC", text)
    cleaned = _CONTROL_CHARS.sub("", cleaned)
    # Angle brackets are removed so users cannot forge our <user_input> delimiters.
    cleaned = cleaned.replace("<", "(").replace(">", ")")
    cleaned = _INJECTION_PATTERN.sub("[removed]", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if not cleaned:
        raise ValueError("Please type something first.")
    return cleaned[:max_chars]


def redact_pii(text: str) -> str:
    """Mask identifiers such as Aadhaar, phone and bank numbers with [LABEL] tokens."""
    for label, pattern in _PII_PATTERNS:
        text = pattern.sub(f"[{label}]", text)
    return text


class PIIRedactingFilter(logging.Filter):
    """Logging filter that redacts PII from the fully formatted message."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_pii(record.getMessage())
        record.args = None
        return True


def get_logger(name: str) -> logging.Logger:
    """Return a logger that always redacts PII."""
    logger = logging.getLogger(name)
    if not any(isinstance(f, PIIRedactingFilter) for f in logger.filters):
        logger.addFilter(PIIRedactingFilter())
    return logger
