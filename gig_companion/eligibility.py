"""Deterministic e-Shram eligibility check (rules from the e-Shram portal, no LLM involved)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ESHRAM_MIN_AGE = 16
ESHRAM_MAX_AGE = 59

Membership = Literal["no", "yes", "unsure"]
Status = Literal["eligible", "not_eligible", "check"]


@dataclass(frozen=True)
class EligibilityResult:
    status: Status
    reasons: tuple[str, ...]


def check_eshram_eligibility(age: int, epfo_esic_nps_member: Membership) -> EligibilityResult:
    """Apply the published e-Shram eligibility rules to a worker's answers."""
    reasons: list[str] = []
    if not ESHRAM_MIN_AGE <= age <= ESHRAM_MAX_AGE:
        reasons.append(f"e-Shram is for workers aged {ESHRAM_MIN_AGE} to {ESHRAM_MAX_AGE}.")
    if epfo_esic_nps_member == "yes":
        reasons.append("Members of EPFO, ESIC or NPS cannot register on e-Shram.")
    if reasons:
        return EligibilityResult("not_eligible", tuple(reasons))
    if epfo_esic_nps_member == "unsure":
        return EligibilityResult(
            "check",
            ("Check your payslip or call 14434 to confirm you are not in EPFO, ESIC or NPS.",),
        )
    return EligibilityResult("eligible", ("You meet the basic e-Shram rules. Follow the steps below.",))
