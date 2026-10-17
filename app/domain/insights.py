"""Best-hours insight: net hourly earnings by time of day and day of week, from the
worker's own log, so they can choose fewer, better hours.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from .constants import BEST_HOURS_MIN_ENTRIES, HOURS_IN_DAY, TIME_BUCKETS
from .earnings import EarningEntry, ExpenseEntry
from .money import ZERO, Number, q, safe_div


class Bucket(BaseModel):
    key: str
    entries: int
    hours: Number
    net: Number
    net_hourly: Number | None


class BestHours(BaseModel):
    enough_data: bool
    min_entries: int
    by_time: list[Bucket]
    by_weekday: list[Bucket]
    best_time: str | None
    best_weekday: str | None


WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def time_bucket(start_hour: int) -> str:
    """Map a start hour (0-23) to morning/afternoon/evening/night."""
    hour = start_hour if start_hour >= TIME_BUCKETS[0][1] else start_hour + HOURS_IN_DAY
    for key, start, end in TIME_BUCKETS:
        if start <= hour < end:
            return key
    return TIME_BUCKETS[-1][0]


def _entry_net(entry: EarningEntry, day_hours: dict[date, Decimal], day_costs: dict[date, Decimal]) -> Decimal:
    """Entry gross minus its share of that day's costs (shared in proportion to hours)."""
    hours = day_hours.get(entry.day, ZERO)
    share = entry.hours / hours if hours else ZERO
    return entry.gross - day_costs.get(entry.day, ZERO) * share


def _collect(groups: dict[str, list[tuple[Decimal, Decimal]]], order: tuple[str, ...]) -> list[Bucket]:
    buckets = []
    for key in order:
        items = groups.get(key, [])
        hours = sum((h for h, _ in items), ZERO)
        net = q(sum((n for _, n in items), ZERO))
        buckets.append(Bucket(key=key, entries=len(items), hours=hours, net=net, net_hourly=safe_div(net, hours)))
    return buckets


def _best(buckets: list[Bucket]) -> str | None:
    ranked = [b for b in buckets if b.entries >= BEST_HOURS_MIN_ENTRIES and b.net_hourly is not None]
    return max(ranked, key=lambda b: b.net_hourly or ZERO).key if ranked else None


def best_hours(entries: list[EarningEntry], expenses: list[ExpenseEntry]) -> BestHours:
    """Rank time-of-day and weekday buckets by net earnings per hour."""
    day_hours: defaultdict[date, Decimal] = defaultdict(Decimal)
    day_costs: defaultdict[date, Decimal] = defaultdict(Decimal)
    for entry in entries:
        day_hours[entry.day] += entry.hours
    for expense in expenses:
        day_costs[expense.day] += expense.amount

    by_time: defaultdict[str, list[tuple[Decimal, Decimal]]] = defaultdict(list)
    by_day: defaultdict[str, list[tuple[Decimal, Decimal]]] = defaultdict(list)
    for entry in entries:
        if not entry.hours:
            continue
        net = _entry_net(entry, day_hours, day_costs)
        by_day[WEEKDAYS[entry.day.weekday()]].append((entry.hours, net))
        if entry.start_hour is not None:
            by_time[time_bucket(entry.start_hour)].append((entry.hours, net))

    time_list = _collect(by_time, tuple(key for key, _, _ in TIME_BUCKETS))
    day_list = _collect(by_day, WEEKDAYS)
    best_time, best_day = _best(time_list), _best(day_list)
    return BestHours(
        enough_data=best_time is not None or best_day is not None,
        min_entries=BEST_HOURS_MIN_ENTRIES,
        by_time=time_list,
        by_weekday=day_list,
        best_time=best_time,
        best_weekday=best_day,
    )
