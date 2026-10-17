"""Opt-in diagnostic reports (Fix-It Tier B intake)."""

from __future__ import annotations

from fastapi import APIRouter

from app.reports import DiagnosticReport, ReportResult

from .deps import ReportsDep

router = APIRouter(prefix="/api", tags=["report"])


@router.post("/report")
async def report(req: DiagnosticReport, reports: ReportsDep) -> ReportResult:
    return await reports.submit(req)
