"""Fix-It Tier B intake: consented, redacted diagnostics -> structured log and (optionally)
a GitHub issue that counts DISTINCT installs. A single report never changes code; the
offline repair workflow only acts when REPORT_QUORUM distinct installs agree.
"""

from __future__ import annotations

import hashlib
import re
from typing import Final, Literal

import httpx
from pydantic import BaseModel, Field

from app.config import Settings
from app.domain.redaction import sanitize_text
from app.logs import log_event
from app.selfheal.schemas import Category

GITHUB_API: Final = "https://api.github.com"
REPORT_LABEL: Final = "user-report"
QUORUM_LABEL: Final = "quorum-reached"
INSTALLS_MARKER: Final = re.compile(r"<!-- installs:([0-9a-f,]*) -->")
DESCRIPTION_CHARS: Final = 300
HASH_CHARS: Final = 16
GITHUB_TIMEOUT_SECONDS: Final = 10.0


class DiagnosticReport(BaseModel):
    consent: Literal[True]
    category: Category
    route: str = Field(pattern=r"^[a-z_-]{1,30}$")
    app_version: str = Field(pattern=r"^[0-9][0-9a-z.+-]{0,20}$")
    error_codes: list[str] = Field(default_factory=list, max_length=10)
    description: str = Field(default="", max_length=DESCRIPTION_CHARS * 2)
    device_class: Literal["phone", "tablet", "desktop"]
    install_id: str = Field(pattern=r"^[0-9a-f-]{16,40}$")


class ReportResult(BaseModel):
    accepted: bool
    issue_number: int | None = None
    distinct_installs: int | None = None


def issue_title(category: Category, route: str) -> str:
    return f"[user-report] {category.value} on {route}"


def install_hash(install_id: str) -> str:
    """Store only a hash of the random install id."""
    return hashlib.sha256(install_id.encode()).hexdigest()[:HASH_CHARS]


def merge_installs(body: str, new_hash: str) -> tuple[str, int]:
    """Add an install hash to the issue body marker; return (new body, distinct count)."""
    match = INSTALLS_MARKER.search(body)
    known = set(filter(None, match.group(1).split(","))) if match else set()
    known.add(new_hash)
    marker = f"<!-- installs:{','.join(sorted(known))} -->"
    body = INSTALLS_MARKER.sub(marker, body) if match else f"{body}\n\n{marker}"
    return body, len(known)


def report_line(report: DiagnosticReport, description: str) -> str:
    codes = ", ".join(report.error_codes) or "none"
    return f'- v{report.app_version} · {report.device_class} · errors: {codes} · "{description}"'


class ReportService:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http

    def _headers(self) -> dict[str, str]:
        token = self._settings.github_token.get_secret_value() if self._settings.github_token else ""
        return {"authorization": f"Bearer {token}", "accept": "application/vnd.github+json"}

    async def submit(self, report: DiagnosticReport) -> ReportResult:
        try:
            description = sanitize_text(report.description, DESCRIPTION_CHARS) if report.description.strip() else ""
        except ValueError:
            description = ""
        error_codes = [c for c in report.error_codes if re.fullmatch(r"[A-Z0-9_]{1,30}", c)]
        report = report.model_copy(update={"error_codes": error_codes})
        log_event(
            "user_report",
            category=report.category.value,
            route=report.route,
            app_version=report.app_version,
            device=report.device_class,
            errors=",".join(error_codes),
        )
        if not self._settings.github_enabled:
            return ReportResult(accepted=True)
        try:
            return await self._upsert_issue(report, description)
        except httpx.HTTPError:
            log_event("report_github_failure")
            return ReportResult(accepted=True)

    async def _upsert_issue(self, report: DiagnosticReport, description: str) -> ReportResult:
        repo = self._settings.github_repo
        title = issue_title(report.category, report.route)
        search = await self._http.get(
            f"{GITHUB_API}/repos/{repo}/issues",
            params={"labels": REPORT_LABEL, "state": "open", "per_page": 100},
            headers=self._headers(),
            timeout=GITHUB_TIMEOUT_SECONDS,
        )
        search.raise_for_status()
        existing = next((i for i in search.json() if i.get("title") == title), None)
        line = report_line(report, description)
        new_hash = install_hash(report.install_id)
        if existing is None:
            body, count = merge_installs(f"Redacted user reports (Fix-It Tier B).\n\n{line}", new_hash)
            created = await self._http.post(
                f"{GITHUB_API}/repos/{repo}/issues",
                json={"title": title, "body": body, "labels": [REPORT_LABEL]},
                headers=self._headers(),
                timeout=GITHUB_TIMEOUT_SECONDS,
            )
            created.raise_for_status()
            return ReportResult(accepted=True, issue_number=created.json().get("number"), distinct_installs=count)
        body, count = merge_installs(f"{existing.get('body') or ''}\n{line}", new_hash)
        labels = [REPORT_LABEL] + ([QUORUM_LABEL] if count >= self._settings.report_quorum else [])
        number = existing["number"]
        updated = await self._http.patch(
            f"{GITHUB_API}/repos/{repo}/issues/{number}",
            json={"body": body, "labels": labels},
            headers=self._headers(),
            timeout=GITHUB_TIMEOUT_SECONDS,
        )
        updated.raise_for_status()
        return ReportResult(accepted=True, issue_number=number, distinct_installs=count)
