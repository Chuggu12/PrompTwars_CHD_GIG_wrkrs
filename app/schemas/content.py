"""Schemas for the verified data files in app/data and their localised API views."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.domain.constants import Lang

LocalText = dict[Lang, str]
LocalSteps = dict[Lang, list[str]]


class Engagement(BaseModel):
    single_days: int = Field(gt=0)
    multi_days: int = Field(gt=0)


class DataEntry(BaseModel):
    """One verified-facts record. Every file shares these fields."""

    id: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    title: LocalText
    summary: LocalText = Field(default_factory=dict)
    eligibility: LocalText = Field(default_factory=dict)
    steps: LocalSteps = Field(default_factory=dict)
    official_url: str = Field(pattern=r"^https://[a-z0-9.-]+\.[a-z]{2,}(/[\w./-]*)?$")
    source: str = Field(min_length=3)
    verified_on: date | None
    verified: bool
    kind: str | None = None
    number: str | None = Field(default=None, pattern=r"^\d{3,6}$")
    group: str | None = None
    state: str | None = None
    engagement: Engagement | None = None
    caution_c: Decimal | None = None
    danger_c: Decimal | None = None

    @field_validator("title")
    @classmethod
    def _has_english(cls, value: LocalText) -> LocalText:
        if "en" not in value:
            raise ValueError("title must include English")
        return value

    def needs_verification(self, today: date, stale_days: int) -> bool:
        """True when unverified or last verified more than `stale_days` ago."""
        if not self.verified or self.verified_on is None:
            return True
        return (today - self.verified_on).days > stale_days


class DataFile(BaseModel):
    about: str
    entries: list[DataEntry]


class LocalizedEntry(BaseModel):
    """A data entry rendered in one language, with freshness flags for the UI."""

    id: str
    title: str
    summary: str = ""
    eligibility: str = ""
    steps: list[str] = Field(default_factory=list)
    official_url: str
    source: str
    verified: bool
    verified_on: date | None
    needs_verification: bool
    translated: bool
    kind: str | None = None
    number: str | None = None
    group: str | None = None
    state: str | None = None
    engagement: Engagement | None = None


class ContentResponse(BaseModel):
    name: str
    lang: Lang
    about: str
    entries: list[LocalizedEntry]
