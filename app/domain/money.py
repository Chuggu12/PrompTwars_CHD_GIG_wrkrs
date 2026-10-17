"""Decimal money and hours types, rounding and Indian-style formatting."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import AfterValidator, Field, PlainSerializer

from .constants import MAX_AMOUNT, MAX_HOURS_PER_DAY

CENT = Decimal("0.01")
ZERO = Decimal("0")


def q(value: Decimal) -> Decimal:
    """Round to 2 decimal places, half-up (the way people round rupees)."""
    return value.quantize(CENT, ROUND_HALF_UP)


def _to_float(value: Decimal) -> float:
    return float(q(value))


# Inputs: non-negative, bounded, rounded. Outputs: serialised as JSON numbers.
MoneyIn = Annotated[Decimal, Field(ge=0, le=MAX_AMOUNT), AfterValidator(q)]
HoursIn = Annotated[Decimal, Field(ge=0, le=MAX_HOURS_PER_DAY), AfterValidator(q)]
Number = Annotated[Decimal, PlainSerializer(_to_float, return_type=float, when_used="json")]


def safe_div(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    """Division that returns None instead of raising on a zero denominator."""
    return q(numerator / denominator) if denominator else None


def _indian_grouping(rupees: int) -> str:
    """12345678 -> '1,23,45,678' (lakh/crore grouping)."""
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
    return ",".join([*groups, tail])


def format_inr(amount: Decimal, *, signed: bool = False) -> str:
    """Decimal('125000') -> '₹1,25,000'; paise shown only when non-zero."""
    value = q(amount)
    sign = "-" if value < ZERO else ("+" if signed and value > ZERO else "")
    value = abs(value)
    rupees = int(value)
    paise = int((value - rupees) * 100)
    text = f"{sign}₹{_indian_grouping(rupees)}"
    return f"{text}.{paise:02d}" if paise else text


def format_hours(hours: Decimal) -> str:
    """Decimal('8.50') -> '8.5'."""
    return f"{q(hours).normalize():f}"
