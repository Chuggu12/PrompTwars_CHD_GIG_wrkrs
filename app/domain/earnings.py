"""Earnings and expenses: daily totals, deltas, goal progress, net hourly rate,
minimum-wage comparison, monthly summary and a step-by-step recalculation.

All arithmetic uses Decimal. The AI never calculates money.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .constants import GOAL_NEAR_FRACTION, MAX_HOURS_PER_DAY, PERCENT, STANDARD_WORKDAY_HOURS
from .money import ZERO, HoursIn, MoneyIn, Number, format_hours, format_inr, q, safe_div

ExpenseCategory = Literal["fuel", "emi", "data", "maintenance", "parking", "other"]
WEEK_DAYS = 7


class EarningEntry(BaseModel):
    """One shift (or one platform's pay) on a given day."""

    model_config = ConfigDict(frozen=True)

    day: date
    hours: HoursIn
    base_pay: MoneyIn = ZERO
    incentive: MoneyIn = ZERO
    start_hour: int | None = Field(default=None, ge=0, le=23)
    platform: str = Field(default="", max_length=40)

    @property
    def gross(self) -> Decimal:
        return self.base_pay + self.incentive


class ExpenseEntry(BaseModel):
    """A work cost such as fuel or a data recharge."""

    model_config = ConfigDict(frozen=True)

    day: date
    category: ExpenseCategory
    amount: MoneyIn


class DayTotals(BaseModel):
    day: date
    hours: Number = ZERO
    base_pay: Number = ZERO
    incentive: Number = ZERO
    gross: Number = ZERO
    expenses: Number = ZERO
    net: Number = ZERO
    net_hourly: Number | None = None
    expense_breakdown: dict[str, Number] = Field(default_factory=dict)


class GoalProgress(BaseModel):
    goal: Number
    achieved: Number
    remaining: Number
    percent: int
    reached: bool
    near: bool


class MinWageCheck(BaseModel):
    min_wage_daily: Number
    hourly_floor: Number
    net_hourly: Number | None
    below: bool


class EarningsSummary(BaseModel):
    today: DayTotals
    yesterday: DayTotals
    delta_net: Number
    delta_gross: Number
    delta_hours: Number
    week_net: Number
    week_hours: Number
    goal: GoalProgress | None = None
    min_wage: MinWageCheck | None = None


class ExplainStep(BaseModel):
    key: str
    expression: str
    result: str


class MonthSummary(BaseModel):
    year: int
    month: int
    days_worked: int
    hours: Number
    gross: Number
    incentive: Number
    expenses: Number
    net: Number
    avg_net_per_day: Number | None
    net_hourly: Number | None
    by_platform: dict[str, Number]


def day_totals(entries: Iterable[EarningEntry], expenses: Iterable[ExpenseEntry], day: date) -> DayTotals:
    """Sum one day's work and costs. Raises ValueError if more than 24 hours are logged."""
    day_entries = [e for e in entries if e.day == day]
    hours = sum((e.hours for e in day_entries), ZERO)
    if hours > MAX_HOURS_PER_DAY:
        raise ValueError(f"More than 24 hours recorded for {day.isoformat()}.")
    base = sum((e.base_pay for e in day_entries), ZERO)
    incentive = sum((e.incentive for e in day_entries), ZERO)
    breakdown: defaultdict[str, Decimal] = defaultdict(Decimal)
    for expense in expenses:
        if expense.day == day:
            breakdown[expense.category] += expense.amount
    costs = sum(breakdown.values(), ZERO)
    gross = base + incentive
    net = gross - costs
    return DayTotals(
        day=day,
        hours=hours,
        base_pay=base,
        incentive=incentive,
        gross=gross,
        expenses=costs,
        net=net,
        net_hourly=safe_div(net, hours),
        expense_breakdown=dict(breakdown),
    )


def goal_progress(net: Decimal, goal: Decimal) -> GoalProgress:
    """Progress toward a daily net-earnings goal (goal must be positive)."""
    achieved = max(net, ZERO)
    remaining = max(goal - achieved, ZERO)
    percent = min(int(achieved * PERCENT / goal), int(PERCENT)) if goal else 0
    reached = achieved >= goal
    return GoalProgress(
        goal=goal,
        achieved=achieved,
        remaining=remaining,
        percent=percent,
        reached=reached,
        near=not reached and achieved >= goal * GOAL_NEAR_FRACTION,
    )


def min_wage_check(net_hourly: Decimal | None, min_wage_daily: Decimal) -> MinWageCheck:
    """Compare net hourly earnings with a user-entered daily minimum wage (8-hour day)."""
    floor = q(min_wage_daily / STANDARD_WORKDAY_HOURS)
    return MinWageCheck(
        min_wage_daily=min_wage_daily,
        hourly_floor=floor,
        net_hourly=net_hourly,
        below=net_hourly is not None and net_hourly < floor,
    )


def summarize(
    entries: list[EarningEntry],
    expenses: list[ExpenseEntry],
    today: date,
    goal: Decimal | None = None,
    min_wage_daily: Decimal | None = None,
) -> EarningsSummary:
    """Today vs yesterday, 7-day totals, goal progress and minimum-wage comparison."""
    now = day_totals(entries, expenses, today)
    before = day_totals(entries, expenses, today - timedelta(days=1))
    week = [day_totals(entries, expenses, today - timedelta(days=i)) for i in range(WEEK_DAYS)]
    return EarningsSummary(
        today=now,
        yesterday=before,
        delta_net=now.net - before.net,
        delta_gross=now.gross - before.gross,
        delta_hours=now.hours - before.hours,
        week_net=sum((d.net for d in week), ZERO),
        week_hours=sum((d.hours for d in week), ZERO),
        goal=goal_progress(now.net, goal) if goal else None,
        min_wage=min_wage_check(now.net_hourly, min_wage_daily) if min_wage_daily else None,
    )


def explain_day(entries: list[EarningEntry], expenses: list[ExpenseEntry], day: date) -> list[ExplainStep]:
    """Show the calculation for one day step by step, in plain arithmetic."""
    totals = day_totals(entries, expenses, day)
    day_entries = [e for e in entries if e.day == day]
    steps: list[ExplainStep] = []
    if day_entries:
        steps.append(_join_step("hours", [e.hours for e in day_entries], totals.hours, unit="h"))
        steps.append(_join_step("base_pay", [e.base_pay for e in day_entries], totals.base_pay))
        if totals.incentive:
            steps.append(_join_step("incentive", [e.incentive for e in day_entries], totals.incentive))
    steps.append(
        ExplainStep(
            key="gross",
            expression=f"{format_inr(totals.base_pay)} + {format_inr(totals.incentive)}",
            result=format_inr(totals.gross),
        )
    )
    for category, amount in totals.expense_breakdown.items():
        steps.append(ExplainStep(key=f"expense_{category}", expression=f"- {format_inr(amount)}", result=""))
    steps.append(
        ExplainStep(
            key="net",
            expression=f"{format_inr(totals.gross)} - {format_inr(totals.expenses)}",
            result=format_inr(totals.net),
        )
    )
    if totals.net_hourly is not None:
        steps.append(
            ExplainStep(
                key="net_hourly",
                expression=f"{format_inr(totals.net)} ÷ {format_hours(totals.hours)} h",
                result=format_inr(totals.net_hourly),
            )
        )
    return steps


def _join_step(key: str, parts: list[Decimal], total: Decimal, unit: str = "") -> ExplainStep:
    if unit:
        expression = " + ".join(f"{format_hours(p)} {unit}" for p in parts)
        result = f"{format_hours(total)} {unit}"
    else:
        expression = " + ".join(format_inr(p) for p in parts)
        result = format_inr(total)
    return ExplainStep(key=key, expression=expression, result=result)


QUARTER_HOUR = Decimal("0.25")
SECONDS_PER_HOUR = Decimal(3600)


class ShiftHoursInput(BaseModel):
    start: datetime
    end: datetime


class ShiftHours(BaseModel):
    hours: Number
    start_hour: int
    day: date


def shift_hours(data: ShiftHoursInput) -> ShiftHours:
    """Hours between shift start and end, rounded to the nearest quarter hour (max 24)."""
    seconds = Decimal(max((data.end - data.start).total_seconds(), 0))
    hours = min((seconds / SECONDS_PER_HOUR / QUARTER_HOUR).to_integral_value() * QUARTER_HOUR, MAX_HOURS_PER_DAY)
    return ShiftHours(hours=hours, start_hour=data.start.hour, day=data.start.date())


def month_summary(entries: list[EarningEntry], expenses: list[ExpenseEntry], year: int, month: int) -> MonthSummary:
    """Totals for one calendar month (for a lender or personal review)."""
    month_entries = [e for e in entries if e.day.year == year and e.day.month == month]
    month_costs = [x for x in expenses if x.day.year == year and x.day.month == month]
    days = {e.day for e in month_entries if e.hours or e.gross}
    hours = sum((e.hours for e in month_entries), ZERO)
    gross = sum((e.gross for e in month_entries), ZERO)
    costs = sum((x.amount for x in month_costs), ZERO)
    net = gross - costs
    by_platform: defaultdict[str, Decimal] = defaultdict(Decimal)
    for entry in month_entries:
        by_platform[entry.platform or "other"] += entry.gross
    return MonthSummary(
        year=year,
        month=month,
        days_worked=len(days),
        hours=hours,
        gross=gross,
        incentive=sum((e.incentive for e in month_entries), ZERO),
        expenses=costs,
        net=net,
        avg_net_per_day=safe_div(net, Decimal(len(days))),
        net_hourly=safe_div(net, hours),
        by_platform=dict(by_platform),
    )
