"""Document vault expiry tracking and calendar (.ics) reminders."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from .constants import DOC_REMINDER_OFFSETS, DOC_SOON_DAYS, DOC_URGENT_DAYS

DocKind = Literal["licence", "id", "vehicle_rc", "insurance", "puc", "permit", "other"]
ExpiryStatus = Literal["expired", "urgent", "soon", "ok"]


class DocItem(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    kind: DocKind
    label: str = Field(default="", max_length=60)
    expires_on: date


class DocExpiry(BaseModel):
    id: str
    kind: DocKind
    days_left: int
    status: ExpiryStatus
    remind_on: list[date]


def expiry_status(days_left: int) -> ExpiryStatus:
    if days_left < 0:
        return "expired"
    if days_left <= DOC_URGENT_DAYS:
        return "urgent"
    if days_left <= DOC_SOON_DAYS:
        return "soon"
    return "ok"


def expiries(docs: list[DocItem], today: date) -> list[DocExpiry]:
    """Days left and future reminder dates for each document, soonest first."""
    result = []
    for doc in docs:
        days_left = (doc.expires_on - today).days
        reminders = [doc.expires_on - timedelta(days=d) for d in DOC_REMINDER_OFFSETS]
        result.append(
            DocExpiry(
                id=doc.id,
                kind=doc.kind,
                days_left=days_left,
                status=expiry_status(days_left),
                remind_on=[r for r in reminders if r >= today],
            )
        )
    return sorted(result, key=lambda d: d.days_left)


def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", " ")


def to_ics(docs: list[DocItem], today: date, titles: dict[str, str]) -> str:
    """iCalendar text with an all-day reminder event per reminder date."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Rozi//Document reminders//EN", "CALSCALE:GREGORIAN"]
    for item in expiries(docs, today):
        doc = next(d for d in docs if d.id == item.id)
        title = _ics_escape(f"{titles.get(doc.kind, doc.kind)} {doc.label}".strip())
        for when in item.remind_on:
            lines += [
                "BEGIN:VEVENT",
                f"UID:{doc.id}-{when.isoformat()}@rozi.local",
                f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{when.strftime('%Y%m%d')}",
                f"SUMMARY:{title} - {doc.expires_on.isoformat()}",
                "END:VEVENT",
            ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
