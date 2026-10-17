"""Deterministic fallbacks and output guards for AI features.

Fallbacks use only the worker's real input and verified data; they never invent content.
Guards reject AI output that adds or drops numbers or links.
"""

from __future__ import annotations

import re
import unicodedata
from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Final

from app.domain.letters import GrievanceFacts, IssueType, Remedy

from .schemas import DayGist

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_LINK = re.compile(r"(?:https?://)?(?:[a-z0-9-]+\.)+(?:in|org|com|net|gov)(?:/[^\s)\]]*)?", re.IGNORECASE)

_AMOUNT = re.compile(
    r"(?:₹|\brs\.?|\binr|रुपये|रुपए|ரூபாய்|ਰੁਪਏ)\s*(\d[\d,]*(?:\.\d+)?)"
    r"|(\d[\d,]*(?:\.\d+)?)\s*(?:rupees?|rs\b|रुपये|रुपए|ரூபாய்|ਰੁਪਏ)",
    re.IGNORECASE,
)
_HOURS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|घंटे|घंटा|மணி|ਘੰਟੇ|ਘੰਟਾ)", re.IGNORECASE)
_DMY = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

_RELATIVE_DAYS: Final[dict[int, tuple[str, ...]]] = {
    0: ("today", "आज", "இன்று", "ਅੱਜ"),
    1: ("yesterday", "कल", "நேற்று", "ਕੱਲ੍ਹ"),
}
_ISSUE_WORDS: Final[dict[IssueType, tuple[str, ...]]] = {
    "unfair_deactivation": ("deactivat", "blocked", "id band", "account band", "बंद", "ब्लॉक", "முடக்க", "ਬੰਦ", "ਬਲੌਕ"),
    "bonus_denial": ("incentive", "bonus", "इंसेंटिव", "बोनस", "ஊக்கத்தொகை", "போனஸ்", "ਇੰਸੈਂਟਿਵ", "ਬੋਨਸ"),
    "wage_theft": ("wage", "salary", "contractor", "thekedar", "मज़दूरी", "मजदूरी", "ठेकेदार", "கூலி", "ਮਜ਼ਦੂਰੀ", "ਠੇਕੇਦਾਰ"),
    "payment_delay": ("payment", "not paid", "late", "pending", "भुगतान", "पेमेंट", "पैसे नहीं", "பணம்", "ਭੁਗਤਾਨ", "ਪੇਮੈਂਟ"),
    "explanation_request": ("rating", "why", "reason", "रेटिंग", "क्यों", "மதிப்பீடு", "ஏன்", "ਰੇਟਿੰਗ", "ਕਿਉਂ"),
}
DEFAULT_REMEDY: Final[dict[IssueType, Remedy]] = {
    "payment_delay": "pay_dues",
    "unfair_deactivation": "reactivate",
    "bonus_denial": "pay_bonus",
    "wage_theft": "pay_dues",
    "explanation_request": "written_explanation",
    "other": "other",
}
_ACCIDENT = re.compile(r"accident|injur|दुर्घटना|एक्सीडेंट|चोट|விபத்து|காயம்|ਹਾਦਸਾ|ਦੁਰਘਟਨਾ|ਸੱਟ", re.IGNORECASE)
_PAYMENT_DELAY = re.compile(r"payment.{0,20}(late|not|pending)|भुगतान|पेमेंट नहीं|பணம் வரவில்லை|ਭੁਗਤਾਨ", re.IGNORECASE)
_OTHER_DELAY = re.compile(r"traffic|wait|delay|जाम|इंतज़ार|देर|போக்குவரத்து|காத்திரு|ਜਾਮ|ਉਡੀਕ|ਦੇਰ", re.IGNORECASE)


def ascii_digits(text: str) -> str:
    """Convert Devanagari/Tamil/Gurmukhi digits to ASCII so numbers compare equal."""
    return "".join(str(unicodedata.digit(c)) if c.isdigit() and not c.isascii() else c for c in text)


def _norm_number(raw: str) -> str:
    try:
        return format(Decimal(raw.replace(",", "")).normalize(), "f")
    except InvalidOperation:
        return raw


def fact_tokens(text: str) -> set[str]:
    """Numbers and links in a text (normalised) - the facts AI must not change."""
    text = ascii_digits(text)
    links = {
        m.group(0).lower().removeprefix("https://").removeprefix("http://").rstrip("/.") for m in _LINK.finditer(text)
    }
    without_links = _LINK.sub(" ", text)
    return links | {_norm_number(n) for n in _NUMBER.findall(without_links)}


def adds_facts(original: str, new: str) -> bool:
    """True if `new` contains numbers or links that are not in `original`."""
    return not fact_tokens(new) <= fact_tokens(original)


def keeps_facts(original: str, new: str) -> bool:
    """True if `new` has exactly the same numbers and links as `original`."""
    return fact_tokens(new) == fact_tokens(original)


def _parse_date(text: str, today: date) -> date | None:
    for pattern, order in ((_ISO, (0, 1, 2)), (_DMY, (2, 1, 0))):
        match = pattern.search(text)
        if match:
            parts = [int(match.group(i + 1)) for i in order]
            try:
                return date(parts[0], parts[1], parts[2])
            except ValueError:
                continue
    lowered = text.lower()
    for offset, words in sorted(_RELATIVE_DAYS.items(), reverse=True):
        if any(w in lowered for w in words):
            return today - timedelta(days=offset)
    return None


def _first_amount(text: str) -> Decimal | None:
    match = _AMOUNT.search(text)
    if not match:
        return None
    try:
        return Decimal((match.group(1) or match.group(2)).replace(",", ""))
    except InvalidOperation:
        return None


def extract_grievance(text: str, today: date) -> GrievanceFacts:
    """Keyword/regex extraction used when the AI is unavailable. Worker confirms all fields."""
    text = ascii_digits(text)
    lowered = text.lower()
    issue: IssueType = next((kind for kind, words in _ISSUE_WORDS.items() if any(w in lowered for w in words)), "other")
    return GrievanceFacts(
        date=_parse_date(text, today),
        platform=None,
        issue_type=issue,
        amount_lost=_first_amount(text),
        remedy_sought=DEFAULT_REMEDY[issue],
    )


def extract_day_gist(text: str) -> DayGist:
    """Regex extraction of hours, earnings and incidents from a spoken summary."""
    text = ascii_digits(text)
    hours_match = _HOURS.search(text)
    amount = _first_amount(text)
    hours = float(hours_match.group(1)) if hours_match else None
    return DayGist(
        hours=hours if hours is not None and hours <= 24 else None,
        earnings_inr=float(amount) if amount is not None else None,
        accident=bool(_ACCIDENT.search(text)),
        payment_delay=bool(_PAYMENT_DELAY.search(text)),
        other_delay=bool(_OTHER_DELAY.search(text)),
    )


class LRUCache[K, V]:
    """Tiny LRU for successful, non-personal AI results (never degraded ones)."""

    def __init__(self, size: int) -> None:
        self._size = size
        self._data: OrderedDict[K, V] = OrderedDict()

    def get(self, key: K) -> V | None:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def put(self, key: K, value: V) -> None:
        self._data[key] = value
        self._data.move_to_end(key)
        if len(self._data) > self._size:
            self._data.popitem(last=False)
