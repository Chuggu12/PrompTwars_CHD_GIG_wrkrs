"""Fair Pay Check: effective commission, vehicle cost per km, EMI and savings planner.

Results are estimates from the worker's own numbers. Not tax or financial advice.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from .constants import (
    COMMISSION_TOLERANCE_PP,
    MAX_EMI_MONTHS,
    MAX_INTEREST_PCT,
    MONTHS_PER_YEAR,
    PERCENT,
    WEEKS_PER_YEAR,
)
from .money import ZERO, MoneyIn, Number, q, safe_div


class CommissionInput(BaseModel):
    gross_fare: MoneyIn = Field(gt=0)
    net_payout: MoneyIn
    stated_pct: Decimal | None = Field(default=None, ge=0, le=PERCENT)

    @model_validator(mode="after")
    def _payout_not_above_fare(self) -> CommissionInput:
        if self.net_payout > self.gross_fare:
            raise ValueError("net_payout cannot be more than gross_fare")
        return self


class CommissionResult(BaseModel):
    deducted: Number
    effective_pct: Number
    stated_pct: Number | None
    difference_pp: Number | None
    higher_than_stated: bool


def commission(data: CommissionInput) -> CommissionResult:
    """Effective commission = (fare - payout) / fare, compared with the stated rate."""
    deducted = data.gross_fare - data.net_payout
    effective = q(deducted * PERCENT / data.gross_fare)
    difference = q(effective - data.stated_pct) if data.stated_pct is not None else None
    return CommissionResult(
        deducted=deducted,
        effective_pct=effective,
        stated_pct=data.stated_pct,
        difference_pp=difference,
        higher_than_stated=difference is not None and difference > COMMISSION_TOLERANCE_PP,
    )


class CostPerKmInput(BaseModel):
    km: Decimal = Field(gt=0, le=Decimal("100000"))
    fuel: MoneyIn = ZERO
    maintenance: MoneyIn = ZERO
    other: MoneyIn = ZERO


class CostPerKmResult(BaseModel):
    total_cost: Number
    per_km: Number


def cost_per_km(data: CostPerKmInput) -> CostPerKmResult:
    total = data.fuel + data.maintenance + data.other
    return CostPerKmResult(total_cost=total, per_km=q(total / data.km))


class EmiInput(BaseModel):
    principal: MoneyIn = Field(gt=0)
    annual_rate_pct: Decimal = Field(ge=0, le=MAX_INTEREST_PCT)
    months: int = Field(ge=1, le=MAX_EMI_MONTHS)
    months_paid: int = Field(default=0, ge=0, le=MAX_EMI_MONTHS)

    @model_validator(mode="after")
    def _paid_within_term(self) -> EmiInput:
        if self.months_paid > self.months:
            raise ValueError("months_paid cannot exceed months")
        return self


class EmiResult(BaseModel):
    emi: Number
    total_payment: Number
    total_interest: Number
    months_left: int
    remaining_payment: Number


def emi(data: EmiInput) -> EmiResult:
    """Standard reducing-balance EMI: P*r*(1+r)^n / ((1+r)^n - 1)."""
    rate = data.annual_rate_pct / PERCENT / MONTHS_PER_YEAR
    if rate == ZERO:
        monthly = q(data.principal / data.months)
    else:
        growth = (1 + rate) ** data.months
        monthly = q(data.principal * rate * growth / (growth - 1))
    total = monthly * data.months
    months_left = data.months - data.months_paid
    return EmiResult(
        emi=monthly,
        total_payment=total,
        total_interest=total - data.principal,
        months_left=months_left,
        remaining_payment=monthly * months_left,
    )


class SavingsInput(BaseModel):
    monthly_net: MoneyIn
    percent: Decimal = Field(ge=0, le=PERCENT)


class SavingsResult(BaseModel):
    per_month: Number
    per_week: Number
    per_year: Number


def savings_plan(data: SavingsInput) -> SavingsResult:
    """Money to set aside each month/week for a chosen share of net income."""
    per_month = q(data.monthly_net * data.percent / PERCENT)
    per_year = per_month * MONTHS_PER_YEAR
    per_week = safe_div(per_year, WEEKS_PER_YEAR) or ZERO
    return SavingsResult(per_month=per_month, per_week=per_week, per_year=per_year)
