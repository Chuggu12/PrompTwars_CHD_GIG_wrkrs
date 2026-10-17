"""Stateless alert engine: turns a context snapshot into candidate alerts.

Rules decide WHEN to alert; the copy comes from app/data/alerts-copy.json. The browser
applies frequency caps, quiet hours, cooldowns and snooze. Alerts must help, never
pressure: no false urgency, no "one more order" nudges, no guilt.
"""

from __future__ import annotations

import string
from collections.abc import Callable, Iterator
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from .constants import (
    DAILY_COOLDOWN_MINUTES,
    DOC_SOON_DAYS,
    DOC_URGENT_DAYS,
    FATIGUE_WARN_HOURS,
    GOAL_NEAR_FRACTION,
    RAIN_ALERT_PROBABILITY,
    REST_MODE_HOURS,
    Lang,
)
from .money import ZERO, format_hours, format_inr

Priority = Literal["critical", "important", "nudge"]


class AlertCopy(BaseModel):
    title: str
    body: str
    cta: str = ""


class AlertType(BaseModel):
    priority: Priority
    icon: str
    cooldown_minutes: int = Field(ge=0)
    cta_route: str = Field(default="", pattern=r"^(#/[a-z0-9/_-]*)?$")
    copy_: dict[Lang, AlertCopy] = Field(alias="copy")


class AlertCopyBook(BaseModel):
    types: dict[str, AlertType]


class WeatherSignal(BaseModel):
    rain_probability_max: int = Field(ge=0, le=100)
    rain_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    apparent_max_c: Decimal | None = None
    heat_caution_c: Decimal
    heat_danger_c: Decimal


class DuePayment(BaseModel):
    platform: str = Field(max_length=40)
    due_date: date
    paid: bool = False


class ExpiringDoc(BaseModel):
    kind: str = Field(max_length=20)
    expires_on: date


class EligibilitySignal(BaseModel):
    days: int = Field(ge=0)
    target: int = Field(gt=0)


class AlertContext(BaseModel):
    lang: Lang = "en"
    now: datetime
    hours_today: Decimal = Field(default=ZERO, ge=0, le=24)
    net_today: Decimal = ZERO
    delta_net: Decimal = ZERO
    goal: Decimal | None = Field(default=None, gt=0)
    warn_at: Decimal = FATIGUE_WARN_HOURS
    rest_at: Decimal = REST_MODE_HOURS
    shift_active: bool = False
    weather: WeatherSignal | None = None
    payments: list[DuePayment] = Field(default_factory=list, max_length=50)
    documents: list[ExpiringDoc] = Field(default_factory=list, max_length=50)
    eligibility: EligibilitySignal | None = None
    data_needs_verification: bool = False
    doc_titles: dict[str, str] = Field(default_factory=dict)


class AlertCta(BaseModel):
    label: str
    route: str


class Alert(BaseModel):
    id: str
    type: str
    priority: Priority
    title: str
    body: str
    cta: AlertCta | None
    icon: str
    expires_at: datetime
    dedupe_key: str
    cooldown_minutes: int


Candidate = tuple[str, dict[str, str], str]  # (alert type, template values, dedupe suffix)
Rule = Callable[[AlertContext], Iterator[Candidate]]


def _goal_rules(ctx: AlertContext) -> Iterator[Candidate]:
    if ctx.goal is None:
        return
    achieved = max(ctx.net_today, ZERO)
    if achieved >= ctx.goal:
        yield "goal_reached", {"goal": format_inr(ctx.goal)}, ""
    elif achieved >= ctx.goal * GOAL_NEAR_FRACTION:
        yield "goal_near", {"remaining": format_inr(ctx.goal - achieved)}, ""


def _win_rule(ctx: AlertContext) -> Iterator[Candidate]:
    if not ctx.shift_active and ctx.net_today > ZERO and ctx.delta_net > ZERO:
        yield "win", {"net": format_inr(ctx.net_today), "delta": format_inr(ctx.delta_net)}, ""


def _hours_rules(ctx: AlertContext) -> Iterator[Candidate]:
    hours = {"hours": format_hours(ctx.hours_today)}
    if ctx.hours_today >= ctx.rest_at:
        yield "rest_mode", hours, ""
    elif ctx.hours_today >= ctx.warn_at:
        yield "fatigue", hours, ""


def _weather_rules(ctx: AlertContext) -> Iterator[Candidate]:
    weather = ctx.weather
    if weather is None:
        return
    if weather.rain_probability_max >= RAIN_ALERT_PROBABILITY and weather.rain_time:
        yield "rain", {"time": weather.rain_time}, weather.rain_time
    if weather.apparent_max_c is not None:
        if weather.apparent_max_c >= weather.heat_danger_c:
            yield "heat_danger", {}, ""
        elif weather.apparent_max_c >= weather.heat_caution_c:
            yield "heat", {}, ""


def _payment_rules(ctx: AlertContext) -> Iterator[Candidate]:
    for payment in ctx.payments:
        days = (ctx.now.date() - payment.due_date).days
        if not payment.paid and days > 0:
            values = {"platform": payment.platform or "-", "days": str(days)}
            yield "late_payment", values, f"{payment.platform}:{payment.due_date.isoformat()}"


def _document_rules(ctx: AlertContext) -> Iterator[Candidate]:
    for doc in ctx.documents:
        days = (doc.expires_on - ctx.now.date()).days
        values = {"days": str(max(days, 0)), "document": ctx.doc_titles.get(doc.kind, doc.kind)}
        suffix = f"{doc.kind}:{doc.expires_on.isoformat()}"
        if days < 0:
            yield "document_expired", values, suffix
        elif days <= DOC_SOON_DAYS:
            yield ("document_urgent" if days <= DOC_URGENT_DAYS else "document"), values, suffix


def _eligibility_rule(ctx: AlertContext) -> Iterator[Candidate]:
    if ctx.eligibility and ctx.eligibility.days > 0:
        values = {"days": str(ctx.eligibility.days), "target": str(ctx.eligibility.target)}
        yield "eligibility", values, ""


def _data_rule(ctx: AlertContext) -> Iterator[Candidate]:
    if ctx.data_needs_verification:
        yield "data_outdated", {}, ""


RULES: tuple[Rule, ...] = (
    _hours_rules,
    _weather_rules,
    _payment_rules,
    _document_rules,
    _goal_rules,
    _win_rule,
    _eligibility_rule,
    _data_rule,
)
_PRIORITY_ORDER: dict[Priority, int] = {"critical": 0, "important": 1, "nudge": 2}


def _render(template: str, values: dict[str, str]) -> str:
    names = {name for _, name, _, _ in string.Formatter().parse(template) if name}
    return template.format(**{name: values.get(name, "") for name in names})


def _end_of_day(now: datetime) -> datetime:
    return datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=now.tzinfo)


def build_alert(kind: str, values: dict[str, str], suffix: str, ctx: AlertContext, book: AlertCopyBook) -> Alert:
    """Render one alert from its copy template in the worker's language."""
    spec = book.types[kind]
    copy = spec.copy_.get(ctx.lang) or spec.copy_["en"]
    dedupe = f"{kind}:{ctx.now.date().isoformat()}" + (f":{suffix}" if suffix else "")
    return Alert(
        id=dedupe,
        type=kind,
        priority=spec.priority,
        title=_render(copy.title, values),
        body=_render(copy.body, values),
        cta=AlertCta(label=copy.cta, route=spec.cta_route) if copy.cta and spec.cta_route else None,
        icon=spec.icon,
        expires_at=_end_of_day(ctx.now),
        dedupe_key=dedupe,
        cooldown_minutes=spec.cooldown_minutes or DAILY_COOLDOWN_MINUTES,
    )


def evaluate(ctx: AlertContext, book: AlertCopyBook) -> list[Alert]:
    """All candidate alerts for this context, most important first."""
    alerts = [
        build_alert(kind, values, suffix, ctx, book)
        for rule in RULES
        for kind, values, suffix in rule(ctx)
        if kind in book.types
    ]
    return sorted(alerts, key=lambda a: _PRIORITY_ORDER[a.priority])
