"""Deterministic grievance and request letters built from stored, translated templates.

The AI may extract facts (which the worker confirms) and polish wording later, but the
letter itself always comes from these templates and the worker's own confirmed facts.
"""

from __future__ import annotations

import datetime as dt
import string
from typing import Literal

from pydantic import BaseModel, Field

from .constants import Lang
from .money import MoneyIn, format_inr

IssueType = Literal[
    "payment_delay", "unfair_deactivation", "bonus_denial", "wage_theft", "explanation_request", "other"
]
Remedy = Literal["pay_dues", "reactivate", "pay_bonus", "written_explanation", "human_review", "other"]


class GrievanceFacts(BaseModel):
    """Facts the worker confirms before a letter is built. Also the AI extraction schema."""

    date: dt.date | None = None
    platform: str | None = Field(default=None, max_length=40)
    issue_type: IssueType = "other"
    amount_lost: MoneyIn | None = None
    remedy_sought: Remedy = "other"


class LetterInput(BaseModel):
    facts: GrievanceFacts
    lang: Lang = "en"
    today: dt.date
    worker_name: str = Field(default="", max_length=60)
    worker_id: str = Field(default="", max_length=40)
    summary: str = Field(default="", max_length=800)


class LanguageTemplates(BaseModel):
    salutation: str
    subject: dict[IssueType, str]
    issue: dict[IssueType, str]
    remedy: dict[Remedy, str]
    details_label: str
    closing: str
    references_label: str
    unknown: str
    review_note: str


class LetterTemplates(BaseModel):
    languages: dict[Lang, LanguageTemplates]
    references: dict[IssueType, list[str]]


class Citation(BaseModel):
    id: str
    title: str
    official_url: str
    verified: bool


class Letter(BaseModel):
    lang: Lang
    subject: str
    body: str
    references: list[Citation]
    review_note: str


class _Blank(dict[str, str]):
    """format_map helper: unknown placeholders render as an empty string."""

    def __missing__(self, key: str) -> str:
        return ""


def _fill(template: str, values: dict[str, str]) -> str:
    allowed = {name for _, name, _, _ in string.Formatter().parse(template) if name}
    return template.format_map(_Blank({k: v for k, v in values.items() if k in allowed}))


def build_letter(data: LetterInput, templates: LetterTemplates, citations: dict[str, Citation]) -> Letter:
    """Fill the stored template for the issue type in the chosen language."""
    lang_tpl = templates.languages.get(data.lang) or templates.languages["en"]
    facts = data.facts
    unknown = lang_tpl.unknown
    values = {
        "platform": facts.platform or unknown,
        "date": facts.date.strftime("%d-%m-%Y") if facts.date else unknown,
        "amount": format_inr(facts.amount_lost) if facts.amount_lost is not None else unknown,
        "name": data.worker_name or unknown,
        "worker_id": data.worker_id or unknown,
        "today": data.today.strftime("%d-%m-%Y"),
    }
    refs = [citations[r] for r in templates.references.get(facts.issue_type, []) if r in citations]
    parts = [
        _fill(lang_tpl.salutation, values),
        _fill(lang_tpl.issue[facts.issue_type], values),
    ]
    if data.summary.strip():
        parts.append(f"{lang_tpl.details_label}\n{data.summary.strip()}")
    parts.append(_fill(lang_tpl.remedy[facts.remedy_sought], values))
    if refs:
        parts.append(lang_tpl.references_label + "\n" + "\n".join(f"- {r.title}: {r.official_url}" for r in refs))
    parts.append(_fill(lang_tpl.closing, values))
    return Letter(
        lang=data.lang,
        subject=_fill(lang_tpl.subject[facts.issue_type], values),
        body="\n\n".join(parts),
        references=refs,
        review_note=lang_tpl.review_note,
    )
