"""Deterministic earnings maths. The LLM never calculates money.

All arithmetic uses `Decimal` to avoid floating-point rounding errors on rupee values.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

MONEY = Decimal("0.01")
ZERO = Decimal("0")
MAX_HOURS_PER_DAY = Decimal("24")


def _to_decimal(value: object) -> Decimal:
    """Convert int/float/str/Decimal to Decimal via str() to avoid float artefacts."""
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"Not a valid number: {value!r}") from exc


@dataclass(frozen=True)
class WorkEntry:
    """One shift or one platform's earnings on a given day."""

    day: date
    hours: Decimal
    earnings: Decimal
    platform: str = ""

    def __post_init__(self) -> None:
        hours = _to_decimal(self.hours).quantize(MONEY, ROUND_HALF_UP)
        earnings = _to_decimal(self.earnings).quantize(MONEY, ROUND_HALF_UP)
        if not ZERO <= hours <= MAX_HOURS_PER_DAY:
            raise ValueError("Hours must be between 0 and 24.")
        if earnings < ZERO:
            raise ValueError("Earnings cannot be negative.")
        object.__setattr__(self, "hours", hours)
        object.__setattr__(self, "earnings", earnings)
        object.__setattr__(self, "platform", self.platform.strip()[:40])


@dataclass(frozen=True)
class DayTotals:
    day: date
    hours: Decimal = ZERO
    earnings: Decimal = ZERO


@dataclass(frozen=True)
class EarningsReport:
    """Everything the UI and the LLM insight need — all pre-computed."""

    today: DayTotals
    yesterday: DayTotals
    earnings_delta: Decimal
    hours_delta: Decimal
    hourly_rate_today: Decimal | None
    week_earnings: Decimal
    week_hours: Decimal
    daily_target: Decimal | None
    target_gap: Decimal | None  # > 0: still needed; <= 0: target reached

    @property
    def has_today(self) -> bool:
        return self.today.hours > ZERO or self.today.earnings > ZERO


def aggregate_by_day(entries: Iterable[WorkEntry]) -> dict[date, DayTotals]:
    """Sum hours and earnings per day. Raises ValueError if a day exceeds 24 hours."""
    hours: defaultdict[date, Decimal] = defaultdict(Decimal)
    earnings: defaultdict[date, Decimal] = defaultdict(Decimal)
    for entry in entries:
        hours[entry.day] += entry.hours
        earnings[entry.day] += entry.earnings
    for day, total in hours.items():
        if total > MAX_HOURS_PER_DAY:
            raise ValueError(f"More than 24 hours recorded for {day.isoformat()}.")
    return {day: DayTotals(day, hours[day], earnings[day]) for day in hours}


def build_report(entries: Iterable[WorkEntry], today: date, daily_target: Decimal | None = None) -> EarningsReport:
    """Compute today's totals, delta vs yesterday, 7-day running totals and target gap."""
    by_day = aggregate_by_day(entries)
    yesterday_date = today - timedelta(days=1)
    today_totals = by_day.get(today, DayTotals(today))
    yesterday_totals = by_day.get(yesterday_date, DayTotals(yesterday_date))

    week_start = today - timedelta(days=6)
    week = [totals for day, totals in by_day.items() if week_start <= day <= today]

    rate = (
        (today_totals.earnings / today_totals.hours).quantize(MONEY, ROUND_HALF_UP)
        if today_totals.hours > ZERO
        else None
    )
    target = _to_decimal(daily_target).quantize(MONEY) if daily_target else None
    gap = (target - today_totals.earnings) if target is not None else None

    return EarningsReport(
        today=today_totals,
        yesterday=yesterday_totals,
        earnings_delta=today_totals.earnings - yesterday_totals.earnings,
        hours_delta=today_totals.hours - yesterday_totals.hours,
        hourly_rate_today=rate,
        week_earnings=sum((t.earnings for t in week), ZERO),
        week_hours=sum((t.hours for t in week), ZERO),
        daily_target=target,
        target_gap=gap,
    )


def _indian_grouping(rupees: int) -> str:
    """12345678 -> '1,23,45,678' (Indian lakh/crore grouping)."""
    digits = str(rupees)
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


def format_inr(amount: Decimal, *, signed: bool = False) -> str:
    """Format rupees: Decimal('1250') -> '₹1,250'; signed=True adds '+' to positives."""
    value = _to_decimal(amount).quantize(MONEY, ROUND_HALF_UP)
    sign = "-" if value < ZERO else ("+" if signed and value > ZERO else "")
    value = abs(value)
    rupees = int(value)
    paise = int((value - rupees) * 100)
    text = f"{sign}₹{_indian_grouping(rupees)}"
    return f"{text}.{paise:02d}" if paise else text


def format_hours(hours: Decimal, *, signed: bool = False) -> str:
    """Decimal('2') -> '2 hrs', Decimal('1') -> '1 hr', Decimal('-1.5') -> '-1.5 hrs'."""
    value = _to_decimal(hours)
    sign = "-" if value < ZERO else ("+" if signed and value > ZERO else "")
    magnitude = abs(value).normalize()
    number = f"{magnitude:f}"
    unit = "hr" if magnitude == 1 else "hrs"
    return f"{sign}{number} {unit}"


def format_delta(report: EarningsReport) -> str:
    """'+₹120 / +2 hrs vs yesterday' style summary."""
    return (
        f"{format_inr(report.earnings_delta, signed=True)} / "
        f"{format_hours(report.hours_delta, signed=True)} vs yesterday"
    )


def deterministic_insight(report: EarningsReport) -> str:
    """Rule-based plain-language insight; also the fallback when AI output is unsafe."""
    if not report.has_today:
        return "No work recorded for today yet. Add your hours and earnings to see your progress."

    hours_diff = abs(report.hours_delta)
    if report.hours_delta > ZERO:
        hours_text = f"You worked {format_hours(hours_diff)} more."
    elif report.hours_delta < ZERO:
        hours_text = f"You worked {format_hours(hours_diff)} fewer."
    else:
        hours_text = "You worked the same hours."

    if report.earnings_delta > ZERO:
        parts = [f"You earned {format_inr(report.earnings_delta)} more than yesterday.", hours_text]
    elif report.earnings_delta < ZERO:
        parts = [
            f"You earned {format_inr(abs(report.earnings_delta))} less than yesterday.",
            hours_text,
            "If it suits you, try adjusting your shift timing or taking a shorter break tomorrow.",
        ]
    else:
        parts = ["You earned the same as yesterday.", hours_text]

    if report.hourly_rate_today is not None:
        parts.append(f"That is about {format_inr(report.hourly_rate_today)} per hour today.")
    if report.target_gap is not None and report.daily_target is not None:
        if report.target_gap > ZERO:
            parts.append(f"You are {format_inr(report.target_gap)} away from your target of {format_inr(report.daily_target)}.")
        else:
            parts.append(f"You reached your daily target of {format_inr(report.daily_target)}.")
    return " ".join(parts)


def allowed_amounts(report: EarningsReport) -> set[Decimal]:
    """Every rupee figure the LLM is allowed to mention (absolute values, 2 dp)."""
    values = [
        report.today.earnings,
        report.yesterday.earnings,
        report.earnings_delta,
        report.week_earnings,
        report.hourly_rate_today,
        report.daily_target,
        report.target_gap,
    ]
    return {abs(v).quantize(MONEY) for v in values if v is not None}
