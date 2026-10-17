"""Alternative gig suggestions.

Category selection is deterministic (skill -> category mapping), so the app always
returns 2-3 real categories. The LLM only explains them in simple language, and its
output is rejected if it mentions any pay figure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .llm import LLMClient, LLMUnavailableError
from .prompts import JOBS_TEMPLATE, SYSTEM_BASE
from .translation import translate

SKILLS: dict[str, str] = {
    "two_wheeler": "Two-wheeler with a valid licence",
    "car": "Car with commercial permit",
    "bicycle": "Bicycle / can deliver on foot",
    "lifting": "Can lift and load heavy items",
    "trade_skill": "Trade skill (electrician, plumber, carpenter)",
    "cleaning": "Cleaning / housekeeping",
    "smartphone": "Smartphone with internet",
}


@dataclass(frozen=True)
class GigCategory:
    key: str
    name: str
    requires: frozenset[str]
    examples: tuple[str, ...]
    how_to_start: str


CATEGORIES: tuple[GigCategory, ...] = (
    GigCategory("quick_commerce", "Quick-commerce grocery delivery", frozenset({"two_wheeler", "bicycle"}),
                ("Blinkit", "Zepto", "Swiggy Instamart"), "Download the partner app and complete KYC."),
    GigCategory("parcel", "Parcel & e-commerce delivery", frozenset({"two_wheeler"}),
                ("Amazon Flex", "Shadowfax", "Ekart"), "Apply on the official partner website or app."),
    GigCategory("bike_taxi", "Bike taxi", frozenset({"two_wheeler"}),
                ("Rapido", "Uber Moto"), "Register on the captain app with licence and RC."),
    GigCategory("food_delivery", "Food delivery", frozenset({"two_wheeler", "bicycle"}),
                ("Swiggy", "Zomato"), "Sign up on the delivery partner app."),
    GigCategory("cab", "Cab driving", frozenset({"car"}),
                ("Uber", "Ola", "Rapido Cab"), "Register as a driver partner with commercial documents."),
    GigCategory("goods_transport", "Goods transport & loading help", frozenset({"lifting"}),
                ("Porter",), "Register as a helper or with a tempo/mini-truck."),
    GigCategory("home_services", "Home repair services", frozenset({"trade_skill"}),
                ("Urban Company",), "Apply as a service professional; skill test and training may apply."),
    GigCategory("home_cleaning", "Home cleaning services", frozenset({"cleaning"}),
                ("Urban Company",), "Apply as a cleaning professional; training may apply."),
)

# Always-available options so at least two suggestions are returned.
FALLBACK_CATEGORIES: tuple[GigCategory, ...] = (
    GigCategory("dark_store", "Dark-store picker / packer", frozenset({"smartphone"}),
                ("Blinkit", "Zepto"), "Ask at a nearby dark store or apply via the company's careers page."),
    GigCategory("warehouse", "Warehouse associate (shift work)", frozenset(),
                ("Amazon", "Flipkart"), "Apply via official careers pages; never pay a joining fee."),
)

_MONEY_RE = re.compile(r"₹|\brs\.?\s*\d|\brupees?\b|\binr\b|\d+\s*(?:per|/)\s*(?:hour|day|order|delivery)", re.IGNORECASE)


def suggest_alternatives(skills: set[str], limit: int = 3) -> list[GigCategory]:
    """Rank categories by skill overlap; pad with fallbacks to return 2-3 options."""
    scored = [(len(c.requires & skills), i, c) for i, c in enumerate(CATEGORIES) if c.requires & skills]
    scored.sort(key=lambda item: (-item[0], item[1]))
    picks = [c for _, _, c in scored[:limit]]
    for fallback in FALLBACK_CATEGORIES:
        if len(picks) >= 2:
            break
        picks.append(fallback)
    return picks


def deterministic_explanation(categories: list[GigCategory]) -> str:
    lines = [
        f"**{c.name}** (e.g. {', '.join(c.examples)}): {c.how_to_start}" for c in categories
    ]
    lines.append("Pay varies by city and platform. Sign up only through official apps or websites.")
    return "\n\n".join(lines)


def explain_alternatives(
    categories: list[GigCategory], skills: set[str], role: str, language: str, llm: LLMClient
) -> str:
    """Simple-language explanation in the worker's language, with no pay figures."""
    fallback = deterministic_explanation(categories)
    skill_text = ", ".join(SKILLS[s] for s in sorted(skills) if s in SKILLS) or "general work"
    category_text = "\n".join(f"- {c.name} (examples: {', '.join(c.examples)})" for c in categories)
    try:
        text = llm.generate(
            JOBS_TEMPLATE.format(role=role, skills=skill_text, categories=category_text),
            system=SYSTEM_BASE,
            temperature=0.3,
        )
    except LLMUnavailableError:
        text = fallback
    if _MONEY_RE.search(text):
        text = fallback  # Never let fabricated pay figures reach the worker.
    return translate(text, language, llm)
