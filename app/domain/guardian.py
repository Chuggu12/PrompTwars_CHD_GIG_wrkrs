"""Guardian: working-hours safety. Warns at a fatigue threshold and enters Rest Mode
at a hard limit. Rest Mode blocks only STARTING a new shift; past data stays usable.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .constants import (
    FATIGUE_WARN_HOURS,
    GUARDIAN_MAX_HOURS,
    GUARDIAN_MIN_HOURS,
    REST_DURATION_HOURS,
    REST_MODE_HOURS,
)
from .money import HoursIn, Number

GuardianLevel = Literal["ok", "warn", "rest"]


class GuardianInput(BaseModel):
    hours_today: HoursIn
    now: datetime
    last_shift_end: datetime | None = None
    warn_at: Decimal = Field(default=FATIGUE_WARN_HOURS, ge=GUARDIAN_MIN_HOURS, le=GUARDIAN_MAX_HOURS)
    rest_at: Decimal = Field(default=REST_MODE_HOURS, ge=GUARDIAN_MIN_HOURS, le=GUARDIAN_MAX_HOURS)

    @model_validator(mode="after")
    def _ordered(self) -> GuardianInput:
        if self.warn_at >= self.rest_at:
            raise ValueError("warn_at must be lower than rest_at")
        return self


class GuardianStatus(BaseModel):
    level: GuardianLevel
    hours_today: Number
    warn_at: Number
    rest_at: Number
    suggest_break: bool
    can_start_shift: bool
    rest_until: datetime | None = None


def evaluate(data: GuardianInput) -> GuardianStatus:
    """Return the Guardian level and whether a new shift may start now."""
    hours = data.hours_today
    if hours >= data.rest_at:
        rest_until = (data.last_shift_end or data.now) + timedelta(hours=REST_DURATION_HOURS)
        return GuardianStatus(
            level="rest",
            hours_today=hours,
            warn_at=data.warn_at,
            rest_at=data.rest_at,
            suggest_break=True,
            can_start_shift=data.now >= rest_until,
            rest_until=rest_until,
        )
    level: GuardianLevel = "warn" if hours >= data.warn_at else "ok"
    return GuardianStatus(
        level=level,
        hours_today=hours,
        warn_at=data.warn_at,
        rest_at=data.rest_at,
        suggest_break=level == "warn",
        can_start_shift=True,
    )
