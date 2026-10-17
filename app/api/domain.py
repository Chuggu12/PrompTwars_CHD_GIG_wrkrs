"""Stateless calculation endpoints. Numbers are processed in memory and never stored or logged."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.constants import MAX_ENTRIES_PER_REQUEST
from app.domain import documents, earnings, eligibility, escalation, fairpay, guardian, insights, letters
from app.domain.money import MoneyIn

from .deps import StoreDep

router = APIRouter(prefix="/api/domain", tags=["domain"])

Entries = list[earnings.EarningEntry]
Expenses = list[earnings.ExpenseEntry]


class _WorkLog(BaseModel):
    entries: Entries = Field(default_factory=list, max_length=MAX_ENTRIES_PER_REQUEST)
    expenses: Expenses = Field(default_factory=list, max_length=MAX_ENTRIES_PER_REQUEST)


class SummaryRequest(_WorkLog):
    today: date
    goal: MoneyIn | None = None
    min_wage_daily: MoneyIn | None = None


class ExplainRequest(_WorkLog):
    day: date


class ExplainResponse(BaseModel):
    totals: earnings.DayTotals
    steps: list[earnings.ExplainStep]


class MonthRequest(_WorkLog):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class WagesRequest(BaseModel):
    entries: list[escalation.WageEntry] = Field(max_length=MAX_ENTRIES_PER_REQUEST)
    today: date


class EngagementRequest(BaseModel):
    work_days: list[eligibility.WorkDay] = Field(max_length=MAX_ENTRIES_PER_REQUEST)
    today: date


class EngagementResponse(eligibility.EngagementProgress):
    verified: bool


class EshramRequest(BaseModel):
    age: int = Field(ge=0, le=120)
    member: eligibility.Membership


class DocsRequest(BaseModel):
    docs: list[documents.DocItem] = Field(max_length=50)
    today: date
    titles: dict[str, str] = Field(default_factory=dict, max_length=20)


@router.post("/earnings/summary")
def earnings_summary(req: SummaryRequest) -> earnings.EarningsSummary:
    return earnings.summarize(req.entries, req.expenses, req.today, req.goal, req.min_wage_daily)


@router.post("/earnings/explain")
def earnings_explain(req: ExplainRequest) -> ExplainResponse:
    return ExplainResponse(
        totals=earnings.day_totals(req.entries, req.expenses, req.day),
        steps=earnings.explain_day(req.entries, req.expenses, req.day),
    )


@router.post("/earnings/month")
def earnings_month(req: MonthRequest) -> earnings.MonthSummary:
    return earnings.month_summary(req.entries, req.expenses, req.year, req.month)


@router.post("/shift/hours")
def shift_hours(req: earnings.ShiftHoursInput) -> earnings.ShiftHours:
    return earnings.shift_hours(req)


@router.post("/guardian")
def guardian_status(req: guardian.GuardianInput) -> guardian.GuardianStatus:
    return guardian.evaluate(req)


@router.post("/fairpay/commission")
def commission(req: fairpay.CommissionInput) -> fairpay.CommissionResult:
    return fairpay.commission(req)


@router.post("/fairpay/cost-per-km")
def cost_per_km(req: fairpay.CostPerKmInput) -> fairpay.CostPerKmResult:
    return fairpay.cost_per_km(req)


@router.post("/fairpay/emi")
def emi(req: fairpay.EmiInput) -> fairpay.EmiResult:
    return fairpay.emi(req)


@router.post("/fairpay/savings")
def savings(req: fairpay.SavingsInput) -> fairpay.SavingsResult:
    return fairpay.savings_plan(req)


@router.post("/payments/delay")
def payment_delay(req: escalation.PaymentDelayInput) -> escalation.PaymentDelay:
    return escalation.payment_delay(req)


@router.post("/wages/pending")
def pending_wages(req: WagesRequest) -> escalation.PendingWages:
    return escalation.pending_wages(req.entries, req.today)


@router.post("/eligibility/engagement")
def engagement(req: EngagementRequest, store: StoreDep) -> EngagementResponse:
    single, multi, verified = store.engagement_thresholds()
    progress = eligibility.engagement(req.work_days, req.today, single, multi)
    return EngagementResponse(**progress.model_dump(), verified=verified)


@router.post("/eligibility/eshram")
def eshram(req: EshramRequest) -> eligibility.EshramCheck:
    return eligibility.check_eshram(req.age, req.member)


@router.post("/insights/best-hours")
def best_hours(req: _WorkLog) -> insights.BestHours:
    return insights.best_hours(req.entries, req.expenses)


@router.post("/documents/expiry")
def document_expiry(req: DocsRequest) -> list[documents.DocExpiry]:
    return documents.expiries(req.docs, req.today)


@router.post("/documents/ics")
def document_ics(req: DocsRequest) -> Response:
    text = documents.to_ics(req.docs, req.today, req.titles)
    return Response(
        content=text,
        media_type="text/calendar; charset=utf-8",
        headers={"content-disposition": 'attachment; filename="document-reminders.ics"'},
    )


@router.post("/grievance/letter")
def grievance_letter(req: letters.LetterInput, store: StoreDep) -> letters.Letter:
    return letters.build_letter(req, store.letters, store.citations(req.lang))
