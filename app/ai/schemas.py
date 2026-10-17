"""Input and output models for every AI feature. Outputs double as Gemini response schemas."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.constants import MAX_TEXT_CHARS
from app.domain.constants import Lang
from app.domain.letters import GrievanceFacts, IssueType, Remedy

ReadingLevel = Literal["simple", "standard"]

# ---- requests -------------------------------------------------------------------------


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS * 2)
    target: Lang
    source: Lang | None = None


class SimplifyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    lang: Lang = "en"


class GrievanceExtractRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    lang: Lang = "en"
    today: date


class PolishRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=MAX_TEXT_CHARS * 3)
    lang: Lang = "en"


class WelfareSummaryRequest(BaseModel):
    scheme_id: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    lang: Lang = "en"
    level: ReadingLevel = "simple"


class DayGistRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=1000)
    lang: Lang = "en"
    today: date


# ---- outputs (also sent to Gemini as response schemas) ---------------------------------


class TextOut(BaseModel):
    text: str


class GrievanceAIOut(BaseModel):
    """Plain types only, so the schema converts cleanly for Gemini."""

    incident_date: str | None = Field(default=None, description="YYYY-MM-DD if stated or clearly implied")
    platform: str | None = Field(default=None, description="Company or app name if stated")
    issue_type: IssueType
    amount_lost_inr: float | None = Field(default=None, description="Only if the worker states it")
    remedy_sought: Remedy


class GrievanceDraft(BaseModel):
    facts: GrievanceFacts
    summary: str = Field(description="The worker's own description with personal numbers removed")


class LetterText(BaseModel):
    subject: str
    body: str


class WelfareSummary(BaseModel):
    scheme_id: str
    summary: str
    steps: list[str]
    official_url: str
    needs_verification: bool


class WelfareAIOut(BaseModel):
    summary: str
    steps: list[str]


class DayGist(BaseModel):
    hours: float | None = Field(default=None, ge=0, le=24)
    earnings_inr: float | None = Field(default=None, ge=0, le=1_000_000)
    platform: str | None = Field(default=None, max_length=40)
    accident: bool = False
    payment_delay: bool = False
    other_delay: bool = False


class Clause(BaseModel):
    title: str = Field(max_length=80)
    explanation: str = Field(max_length=400)
    caution: bool = False


class ContractExplanation(BaseModel):
    clauses: list[Clause] = Field(max_length=3)
    readable: bool = True
