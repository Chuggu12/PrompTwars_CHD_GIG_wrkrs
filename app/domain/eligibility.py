"""Eligibility helpers: e-Shram basic rules and engagement-day counting per platform.

Thresholds are passed in from welfare-schemes.json (with a verified flag), never hardcoded.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from .constants import ESHRAM_MAX_AGE, ESHRAM_MIN_AGE, FY_START_MONTH, PERCENT

Membership = Literal["no", "yes", "unsure"]
EshramStatus = Literal["eligible", "not_eligible", "check"]


class EshramCheck(BaseModel):
    status: EshramStatus
    reasons: list[str]


def check_eshram(age: int, epfo_esic_nps_member: Membership) -> EshramCheck:
    """Apply the published e-Shram basic rules (age band, not in EPFO/ESIC/NPS)."""
    reasons: list[str] = []
    if not ESHRAM_MIN_AGE <= age <= ESHRAM_MAX_AGE:
        reasons.append("age_out_of_range")
    if epfo_esic_nps_member == "yes":
        reasons.append("member_epfo_esic_nps")
    if reasons:
        return EshramCheck(status="not_eligible", reasons=reasons)
    if epfo_esic_nps_member == "unsure":
        return EshramCheck(status="check", reasons=["confirm_membership"])
    return EshramCheck(status="eligible", reasons=["basic_rules_met"])


def financial_year(today: date) -> tuple[date, date]:
    """Indian financial year (1 April to 31 March) containing `today`."""
    start_year = today.year if today.month >= FY_START_MONTH else today.year - 1
    return date(start_year, FY_START_MONTH, 1), date(start_year + 1, FY_START_MONTH - 1, 31)


class WorkDay(BaseModel):
    day: date
    platform: str = Field(min_length=1, max_length=40)


class PlatformDays(BaseModel):
    platform: str
    days: int


class EngagementProgress(BaseModel):
    fy_start: date
    fy_end: date
    platforms: list[PlatformDays]
    best_single: int
    total_days: int
    single_threshold: int
    multi_threshold: int
    single_pct: int
    multi_pct: int
    threshold_met: bool


def _pct(value: int, target: int) -> int:
    return min(int(value * PERCENT / target), int(PERCENT)) if target else 0


def engagement(
    work_days: list[WorkDay], today: date, single_threshold: int, multi_threshold: int
) -> EngagementProgress:
    """Count distinct engagement days per platform in the current financial year.

    Across platforms each platform-day counts once, matching the draft rule text
    ("days with each aggregator are added"). Check the official portal for the latest rules.
    """
    fy_start, fy_end = financial_year(today)
    per_platform: defaultdict[str, set[date]] = defaultdict(set)
    for item in work_days:
        if fy_start <= item.day <= min(today, fy_end):
            per_platform[item.platform.strip()].add(item.day)
    platforms = sorted(
        (PlatformDays(platform=name, days=len(days)) for name, days in per_platform.items()),
        key=lambda p: (-p.days, p.platform),
    )
    best = platforms[0].days if platforms else 0
    total = sum(p.days for p in platforms)
    return EngagementProgress(
        fy_start=fy_start,
        fy_end=fy_end,
        platforms=platforms,
        best_single=best,
        total_days=total,
        single_threshold=single_threshold,
        multi_threshold=multi_threshold,
        single_pct=_pct(best, single_threshold),
        multi_pct=_pct(total, multi_threshold),
        threshold_met=best >= single_threshold or total >= multi_threshold,
    )
