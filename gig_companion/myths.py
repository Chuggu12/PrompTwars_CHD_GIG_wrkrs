"""Counter-myth layer: detects common gig-work misconceptions in a (English) query.

Detection is rule-based (curated regexes) so it is predictable and testable. The LLM
only personalises the counter-rationale; the fact itself is fixed and source-linked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ESHRAM = r"(e-?\s?shram|shram card|uan card|labour card)"


@dataclass(frozen=True)
class Myth:
    myth_id: str
    patterns: tuple[re.Pattern[str], ...]
    claim: str
    fact: str
    terms: tuple[str, ...]
    source_doc_id: str

    def matches(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in self.patterns)


def _p(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)


MYTHS: tuple[Myth, ...] = (
    Myth(
        myth_id="eshram_fee",
        patterns=_p(
            rf"\b(pay|fee|fees|cost|costs|charge|charges|money|price)\b.*\b{_ESHRAM}",
            rf"\b{_ESHRAM}.*\b(fee|fees|cost|costs|charge|charges|paid|pay)\b",
        ),
        claim="You have to pay money to register on e-Shram.",
        fact="e-Shram registration is free, including at a Common Service Centre (CSC). You only need Aadhaar, "
        "an Aadhaar-linked mobile number and a savings bank account with IFSC code. Do not pay any agent.",
        terms=("UAN", "Aadhaar-linked mobile", "IFSC", "CSC"),
        source_doc_id="eshram_overview",
    ),
    Myth(
        myth_id="gig_not_eligible",
        patterns=_p(
            r"\b(gig|platform|delivery|driver|rider|daily[- ]wage)\b.*\b(not eligible|no benefits?|can'?t get|cannot get|not allowed|don'?t get)\b",
            r"\bno (employer|company)\b.*\b(scheme|benefit|eligible|register)",
        ),
        claim="Gig workers cannot get government schemes because they have no employer.",
        fact="The Code on Social Security, 2020 legally recognises gig and platform workers. e-Shram is open to "
        "gig/platform workers aged 16-59 who are not in EPFO/ESIC/NPS, and no employer is needed.",
        terms=("platform worker", "aggregator", "Code on Social Security, 2020", "UAN"),
        source_doc_id="social_security_code",
    ),
    Myth(
        myth_id="eshram_deactivation",
        patterns=_p(
            rf"\b{_ESHRAM}.*\b(deactivat\w*|block\w*|ban\w*|lose my (id|job|account))",
            rf"\b(deactivat\w*|block\w*|ban\w*)\b.*\b{_ESHRAM}",
        ),
        claim="Registering on e-Shram will get my platform account blocked.",
        fact="e-Shram is a government database run by the Ministry of Labour & Employment. Registration is between "
        "you and the government and does not need your platform's permission.",
        terms=("UAN", "Ministry of Labour & Employment", "platform ID"),
        source_doc_id="eshram_overview",
    ),
    Myth(
        myth_id="partner_no_rights",
        patterns=_p(
            r"\b(partner|not an employee|not employee|contractor|freelancer)\b.*\b(no rights?|can'?t complain|cannot complain|no use)",
            r"\b(can'?t|cannot|no use|pointless)\b.*\bcomplain\w*\b.*\b(platform|company|app)\b",
        ),
        claim="As a 'partner' I have no right to complain against the platform.",
        fact="Even if the app calls you a 'partner', you can raise a grievance with the platform's grievance officer "
        "(keep the ticket number), then on CPGRAMS (pgportal.gov.in). States like Rajasthan (2023) and Karnataka (2025) "
        "have laws for platform-based gig workers that include grievance redressal.",
        terms=("grievance officer", "ticket number", "CPGRAMS", "aggregator"),
        source_doc_id="grievance_channels",
    ),
    Myth(
        myth_id="pmjay_bpl_only",
        patterns=_p(r"\b(ayushman|pm-?jay|health card)\b.*\b(only|just)\b.*\b(bpl|poor|ration)"),
        claim="Ayushman Bharat is only for BPL ration-card holders.",
        fact="PM-JAY eligibility follows official criteria (SECC data and later expansions), not only BPL cards. "
        "The Union Budget 2025-26 announced PM-JAY cover for gig workers registered on e-Shram. Check at "
        "beneficiary.nha.gov.in or call 14555.",
        terms=("PM-JAY", "empanelled hospital", "e-Shram UAN"),
        source_doc_id="pmjay",
    ),
    Myth(
        myth_id="insurance_costly",
        patterns=_p(r"\b(insurance|bima)\b.*\b(expensive|costly|can'?t afford|cannot afford|too much)"),
        claim="Accident insurance is too expensive for gig workers.",
        fact="PMSBY gives ₹2 lakh accident cover (death or full disability) for ₹20 per year, for ages 18-70 "
        "with a savings bank account.",
        terms=("PMSBY", "premium", "auto-debit"),
        source_doc_id="pmsby",
    ),
)


def detect_myth(text: str) -> Myth | None:
    """Return the first myth the text reflects, or None."""
    return next((myth for myth in MYTHS if myth.matches(text)), None)


def fallback_counter_rationale(myth: Myth, role: str) -> str:
    """Deterministic counter-rationale used when the LLM is unavailable."""
    return f'**Common myth:** "{myth.claim}"\n\n**Fact for a {role.lower()}:** {myth.fact}'
