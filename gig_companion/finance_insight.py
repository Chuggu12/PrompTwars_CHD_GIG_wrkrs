"""LLM-written earnings insight with a deterministic safety guard.

The LLM only receives pre-computed figures. Its output is rejected (and replaced by
the rule-based insight) if it mentions any rupee amount not in the report, or if it
promises future earnings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .earnings import MONEY, EarningsReport, allowed_amounts, deterministic_insight, format_hours, format_inr
from .llm import LLMClient, LLMUnavailableError
from .prompts import INSIGHT_TEMPLATE, SYSTEM_BASE
from .translation import translate

_AMOUNT_RE = re.compile(
    r"(?:₹|\brs\.?|\binr)\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*(?:rupees|rs\b)",
    re.IGNORECASE,
)
_PROMISE_RE = re.compile(
    r"\b(you will earn|you'll earn|you will make|guarantee\w*|assured|definitely earn|promise\w*)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class InsightResult:
    text: str
    ai_generated: bool


def amounts_in(text: str) -> set[Decimal]:
    """Extract all rupee amounts mentioned in text."""
    found: set[Decimal] = set()
    for match in _AMOUNT_RE.finditer(text):
        raw = (match.group(1) or match.group(2) or "").replace(",", "")
        try:
            found.add(Decimal(raw).quantize(MONEY))
        except InvalidOperation:
            continue
    return found


def is_insight_safe(text: str, report: EarningsReport) -> bool:
    """True if the text uses only known figures and makes no earnings promises."""
    return amounts_in(text) <= allowed_amounts(report) and not _PROMISE_RE.search(text)


def _facts(report: EarningsReport) -> str:
    lines = [
        f"- Today: {format_hours(report.today.hours)}, {format_inr(report.today.earnings)}",
        f"- Yesterday: {format_hours(report.yesterday.hours)}, {format_inr(report.yesterday.earnings)}",
        f"- Change in earnings vs yesterday: {format_inr(report.earnings_delta, signed=True)}",
        f"- Change in hours vs yesterday: {format_hours(report.hours_delta, signed=True)}",
        f"- Last 7 days total: {format_inr(report.week_earnings)} over {format_hours(report.week_hours)}",
    ]
    if report.hourly_rate_today is not None:
        lines.append(f"- Earnings per hour today: {format_inr(report.hourly_rate_today)}")
    if report.daily_target is not None and report.target_gap is not None:
        status = (
            f"{format_inr(report.target_gap)} still needed" if report.target_gap > 0 else "target reached"
        )
        lines.append(f"- Daily target: {format_inr(report.daily_target)} ({status})")
    return "\n".join(lines)


def generate_insight(report: EarningsReport, role: str, language: str, llm: LLMClient) -> InsightResult:
    """Return a simple-language insight in the worker's language."""
    fallback = deterministic_insight(report)
    if not report.has_today:
        return InsightResult(translate(fallback, language, llm), ai_generated=False)

    prompt = INSIGHT_TEMPLATE.format(role=role, facts=_facts(report))
    try:
        text = llm.generate(prompt, system=SYSTEM_BASE, temperature=0.3)
    except LLMUnavailableError:
        return InsightResult(translate(fallback, language, llm), ai_generated=False)

    if not is_insight_safe(text, report):
        return InsightResult(translate(fallback, language, llm), ai_generated=False)
    return InsightResult(translate(text, language, llm), ai_generated=True)
