"""Loads and validates the verified data files in app/data once at startup."""

from __future__ import annotations

import json
from datetime import date
from functools import cached_property
from pathlib import Path
from typing import Any, Final

from app.constants import CONTENT_STALE_DAYS
from app.domain.alerts import AlertCopyBook
from app.domain.constants import Lang
from app.domain.letters import Citation, LetterTemplates
from app.schemas.content import ContentResponse, DataEntry, DataFile, LocalizedEntry
from app.selfheal.schemas import TriageBook

DATA_DIR: Final = Path(__file__).parent / "data"
CONTENT_FILES: Final = ("welfare-schemes", "helplines", "state-boards", "legal-refs", "heat-thresholds")
ENGAGEMENT_RULE_ID: Final = "gig_engagement_rule"


def _read(name: str) -> Any:
    return json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))


def localize(entry: DataEntry, lang: Lang, today: date) -> LocalizedEntry:
    """Pick the requested language, falling back to English (flagged as not translated)."""
    translated = lang in entry.title
    return LocalizedEntry(
        id=entry.id,
        title=entry.title.get(lang) or entry.title["en"],
        summary=entry.summary.get(lang) or entry.summary.get("en", ""),
        eligibility=entry.eligibility.get(lang) or entry.eligibility.get("en", ""),
        steps=entry.steps.get(lang) or entry.steps.get("en", []),
        official_url=entry.official_url,
        source=entry.source,
        verified=entry.verified,
        verified_on=entry.verified_on,
        needs_verification=entry.needs_verification(today, CONTENT_STALE_DAYS),
        translated=translated,
        kind=entry.kind,
        number=entry.number,
        group=entry.group,
        state=entry.state,
        engagement=entry.engagement,
    )


class ContentStore:
    """Read-only, validated access to app/data. Invalid files fail fast at startup."""

    def __init__(self) -> None:
        self.files: dict[str, DataFile] = {name: DataFile.model_validate(_read(name)) for name in CONTENT_FILES}

    @cached_property
    def alert_copy(self) -> AlertCopyBook:
        return AlertCopyBook.model_validate(_read("alerts-copy"))

    @cached_property
    def triage(self) -> TriageBook:
        return TriageBook.model_validate(_read("triage-keywords"))

    @cached_property
    def letters(self) -> LetterTemplates:
        return LetterTemplates.model_validate(_read("letter-templates"))

    def entry(self, name: str, entry_id: str) -> DataEntry | None:
        return next((e for e in self.files[name].entries if e.id == entry_id), None)

    def localized(self, name: str, lang: Lang, today: date) -> ContentResponse:
        data = self.files[name]
        return ContentResponse(
            name=name, lang=lang, about=data.about, entries=[localize(e, lang, today) for e in data.entries]
        )

    def citations(self, lang: Lang) -> dict[str, Citation]:
        return {
            e.id: Citation(
                id=e.id, title=e.title.get(lang) or e.title["en"], official_url=e.official_url, verified=e.verified
            )
            for e in self.files["legal-refs"].entries
        }

    def engagement_thresholds(self) -> tuple[int, int, bool]:
        """(single-platform days, multi-platform days, verified) from welfare-schemes.json."""
        rule = self.entry("welfare-schemes", ENGAGEMENT_RULE_ID)
        if rule is None or rule.engagement is None:
            raise LookupError("engagement rule missing from welfare-schemes.json")
        return rule.engagement.single_days, rule.engagement.multi_days, rule.verified

    def heat_thresholds(self) -> tuple[float, float]:
        entry = self.files["heat-thresholds"].entries[0]
        if entry.caution_c is None or entry.danger_c is None:
            raise LookupError("heat thresholds missing")
        return float(entry.caution_c), float(entry.danger_c)

    def any_needs_verification(self, today: date) -> bool:
        return any(e.needs_verification(today, CONTENT_STALE_DAYS) for f in self.files.values() for e in f.entries)
