"""Payment Delay Tracker and pending-wages ledger.

The escalation timeline is a SUGGESTED plan for following up, not a legal deadline.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from .constants import ESCALATION_STEPS
from .money import ZERO, MoneyIn, Number

PaymentStatus = Literal["not_due", "due_today", "late"]


class PaymentDelayInput(BaseModel):
    due_date: date
    today: date
    amount: MoneyIn = ZERO
    platform: str = Field(default="", max_length=40)


class EscalationStep(BaseModel):
    key: str
    on_date: date
    reached: bool


class PaymentDelay(BaseModel):
    status: PaymentStatus
    days_late: int
    amount: Number
    platform: str
    steps: list[EscalationStep]
    next_step: str | None


def payment_delay(data: PaymentDelayInput) -> PaymentDelay:
    """Days late and a dated follow-up plan computed from the due date."""
    days_late = max((data.today - data.due_date).days, 0)
    if data.today < data.due_date:
        status: PaymentStatus = "not_due"
    elif days_late == 0:
        status = "due_today"
    else:
        status = "late"
    steps = [
        EscalationStep(key=key, on_date=data.due_date + timedelta(days=offset), reached=days_late >= offset)
        for key, offset in ESCALATION_STEPS
    ]
    reached = [s for s in steps if s.reached]
    return PaymentDelay(
        status=status,
        days_late=days_late,
        amount=data.amount,
        platform=data.platform,
        steps=steps,
        next_step=reached[-1].key if reached else None,
    )


class WageEntry(BaseModel):
    contractor: str = Field(min_length=1, max_length=60)
    day: date
    amount: MoneyIn
    paid: bool = False


class ContractorBalance(BaseModel):
    contractor: str
    owed: Number
    unpaid_days: int
    oldest_unpaid: date | None
    days_pending: int


class PendingWages(BaseModel):
    total_owed: Number
    contractors: list[ContractorBalance]


def pending_wages(entries: list[WageEntry], today: date) -> PendingWages:
    """Money still owed per contractor, oldest first."""
    owed: defaultdict[str, Decimal] = defaultdict(Decimal)
    unpaid_days: defaultdict[str, list[date]] = defaultdict(list)
    for entry in entries:
        owed.setdefault(entry.contractor, ZERO)
        if not entry.paid:
            owed[entry.contractor] += entry.amount
            unpaid_days[entry.contractor].append(entry.day)
    balances = []
    for name, amount in owed.items():
        days = sorted(unpaid_days[name])
        oldest = days[0] if days else None
        balances.append(
            ContractorBalance(
                contractor=name,
                owed=amount,
                unpaid_days=len(days),
                oldest_unpaid=oldest,
                days_pending=(today - oldest).days if oldest else 0,
            )
        )
    balances.sort(key=lambda b: (-b.days_pending, b.contractor))
    return PendingWages(total_owed=sum(owed.values(), ZERO), contractors=balances)
