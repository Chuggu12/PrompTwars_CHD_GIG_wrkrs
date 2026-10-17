"""Verified knowledge base — the ONLY ground truth used for RAG answers.

Every document carries its official source so each answer can cite it. Content is
plain English; translation happens at answer time. Scheme rules change: re-verify
against the cited sources before production use.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Document:
    """One retrievable unit of verified guidance."""

    doc_id: str
    title: str
    category: str  # "welfare" | "safety" | "documents" | "rights"
    source_name: str
    source_url: str
    content: str
    keywords: tuple[str, ...] = ()

    @property
    def searchable_text(self) -> str:
        return " ".join((self.title, self.content, " ".join(self.keywords)))

    @property
    def citation(self) -> str:
        return f"{self.source_name} ({self.source_url})" if self.source_url else self.source_name


ESHRAM_STEPS: tuple[str, ...] = (
    "Go to https://eshram.gov.in or the registration link https://register.eshram.gov.in.",
    'Click "Register" and enter your Aadhaar-linked mobile number.',
    "Complete Aadhaar OTP verification.",
    'Fill personal details (name, date of birth, address, occupation = "Gig/Platform Worker").',
    "Enter bank account details (savings account number + IFSC code).",
    "Submit and download your UAN card.",
    'Use the same UAN to access AB-PMJAY health benefits through the e-Shram "One-Stop-Solution" dashboard.',
)

DOCUMENTS: tuple[Document, ...] = (
    Document(
        doc_id="eshram_overview",
        title="e-Shram registration for gig and platform workers: eligibility, documents, benefits",
        category="welfare",
        source_name="Ministry of Labour & Employment, e-Shram portal",
        source_url="https://eshram.gov.in",
        content=(
            "e-Shram is the national database of unorganised workers run by the Ministry of Labour & Employment. "
            "Gig and platform workers such as delivery partners, drivers and bike-taxi riders can register. "
            "Registration is free of cost - you do not pay any fee, and registration at a Common Service Centre (CSC) is also free. "
            "Eligibility: age 16 to 59 years; not a member of EPFO, ESIC or NPS; an unorganised worker, including a gig or platform worker. "
            "No employer is needed to register. "
            "Documents required: Aadhaar number, Aadhaar-linked mobile number, and savings bank account number with IFSC code. "
            "Benefit: you get a Universal Account Number (UAN) card. e-Shram is integrated with Ayushman Bharat PM-JAY for health cover. "
            "Helpline: 14434 (toll-free, 9 languages, Monday to Saturday). "
            "Website: https://eshram.gov.in. Registration link: https://register.eshram.gov.in."
        ),
        keywords=("shram card", "labour card", "uan", "unorganised", "register", "eligible", "fee", "free", "cost"),
    ),
    Document(
        doc_id="eshram_registration",
        title="How to register on e-Shram step by step",
        category="welfare",
        source_name="Ministry of Labour & Employment, e-Shram portal",
        source_url="https://eshram.gov.in",
        content="Steps to register on e-Shram: "
        + " ".join(f"Step {i}: {step}" for i, step in enumerate(ESHRAM_STEPS, start=1))
        + " Helpline 14434 if you get stuck.",
        keywords=("how to register", "registration process", "apply", "otp", "uan card", "download", "shram card"),
    ),
    Document(
        doc_id="pmjay",
        title="Ayushman Bharat PM-JAY health cover",
        category="welfare",
        source_name="National Health Authority, Ayushman Bharat PM-JAY",
        source_url="https://pmjay.gov.in",
        content=(
            "Ayushman Bharat Pradhan Mantri Jan Arogya Yojana (PM-JAY) gives cashless health cover of up to ₹5 lakh "
            "per family per year for hospital treatment at empanelled hospitals. "
            "Eligibility follows official criteria (SECC data and later expansions), not only BPL ration cards. "
            "The Union Budget 2025-26 announced PM-JAY health cover for gig and platform workers registered on e-Shram. "
            "Check your eligibility at https://beneficiary.nha.gov.in or call the PM-JAY helpline 14555. "
            "Registered e-Shram workers can reach PM-JAY through the e-Shram One-Stop-Solution dashboard."
        ),
        keywords=("ayushman card", "health", "hospital", "treatment", "medical", "doctor", "illness", "bpl"),
    ),
    Document(
        doc_id="pmsby",
        title="Low-cost accident and life insurance: PMSBY and PMJJBY",
        category="welfare",
        source_name="Department of Financial Services, Jan Suraksha",
        source_url="https://jansuraksha.gov.in",
        content=(
            "Pradhan Mantri Suraksha Bima Yojana (PMSBY) gives accident insurance of ₹2 lakh for accidental death or full "
            "disability for a premium of ₹20 per year. Age 18 to 70 with a savings bank account; premium is auto-debited. "
            "Pradhan Mantri Jeevan Jyoti Bima Yojana (PMJJBY) gives life cover of ₹2 lakh for ₹436 per year, age 18 to 50. "
            "You can enrol through your bank branch or net banking."
        ),
        keywords=("insurance", "bima", "accident", "death", "disability", "cheap", "premium", "expensive", "afford"),
    ),
    Document(
        doc_id="pmsym",
        title="Pension for unorganised workers: PM-SYM",
        category="welfare",
        source_name="Ministry of Labour & Employment, PM Shram Yogi Maan-dhan",
        source_url="https://maandhan.in",
        content=(
            "Pradhan Mantri Shram Yogi Maan-dhan (PM-SYM) is a voluntary pension scheme. Age 18 to 40, monthly income up to "
            "₹15,000, and not a member of EPFO, ESIC or NPS. You pay a monthly contribution between ₹55 and ₹200 depending "
            "on your age and the government pays an equal amount. You get a pension of ₹3,000 per month after age 60."
        ),
        keywords=("pension", "old age", "retirement", "maandhan", "60"),
    ),
    Document(
        doc_id="social_security_code",
        title="Legal recognition of gig and platform workers: Code on Social Security, 2020",
        category="rights",
        source_name="Ministry of Labour & Employment, Code on Social Security, 2020",
        source_url="https://labour.gov.in",
        content=(
            "The Code on Social Security, 2020 legally defines 'gig worker' and 'platform worker'. It provides for the "
            "central government to frame social security schemes for them, such as life and disability cover, accident "
            "insurance, health and maternity benefits and old age protection. Aggregators (platform companies) may be "
            "required to contribute 1-2% of annual turnover, capped at 5% of the amount paid to workers. "
            "Being called a 'partner' does not remove this recognition."
        ),
        keywords=("rights", "law", "legal", "partner", "employee", "aggregator", "social security", "eligible"),
    ),
    Document(
        doc_id="state_laws",
        title="State laws for platform-based gig workers (Rajasthan, Karnataka)",
        category="rights",
        source_name="Rajasthan Platform Based Gig Workers (Registration and Welfare) Act, 2023; "
        "Karnataka Platform Based Gig Workers (Social Security and Welfare) Act, 2025",
        source_url="",
        content=(
            "Some states have their own laws for platform-based gig workers. Rajasthan's 2023 Act provides for a welfare "
            "board, registration of gig workers and a welfare fund. Karnataka's 2025 Act provides for a welfare board, a "
            "welfare fee from aggregators, transparency about automated decisions and a grievance redressal system. "
            "Rules and implementation dates vary, so check with your state labour department."
        ),
        keywords=("state", "rajasthan", "karnataka", "welfare board", "rights", "complain", "grievance"),
    ),
    Document(
        doc_id="grievance_channels",
        title="Where to complain: payment issues, deactivation, deductions",
        category="rights",
        source_name="Department of Administrative Reforms & Public Grievances, CPGRAMS",
        source_url="https://pgportal.gov.in",
        content=(
            "Step 1: Raise the issue with the platform's in-app support or grievance officer and note the ticket number. "
            "Step 2: Keep evidence - screenshots of payouts, deduction messages, deactivation notices and chats. "
            "Step 3: If unresolved, file a complaint on CPGRAMS at https://pgportal.gov.in or with your state labour department. "
            "Labour disputes can also be filed on the Samadhan portal at https://samadhan.labour.gov.in. "
            "For guidance, call the e-Shram helpline 14434."
        ),
        keywords=("complain", "complaint", "grievance", "deactivated", "blocked", "payment", "deduction", "penalty", "dispute"),
    ),
    Document(
        doc_id="road_safety",
        title="Road safety for riders and drivers",
        category="safety",
        source_name="Ministry of Road Transport & Highways",
        source_url="https://morth.nic.in",
        content=(
            "Always wear a helmet - it is compulsory for two-wheeler riders and pillion riders under Section 129 of the "
            "Motor Vehicles Act. Do not use your phone by hand while riding or driving; mount it and use voice navigation. "
            "Never jump signals to beat a delivery timer - your life matters more than a deadline. Check brakes, lights and "
            "tyres regularly. Take a short break every 2 hours. Use the SOS button in your app and share live location with "
            "family at night. In an emergency call 112; for an ambulance call 108; women workers can call 181."
        ),
        keywords=("helmet", "accident", "safe", "safety", "road", "night", "sos", "emergency", "phone", "riding", "driving"),
    ),
    Document(
        doc_id="heat_safety",
        title="Working safely in heatwaves",
        category="safety",
        source_name="National Disaster Management Authority, heatwave guidelines",
        source_url="https://ndma.gov.in",
        content=(
            "During a heatwave drink water often even if you are not thirsty, cover your head, wear light cotton clothes and "
            "rest in shade, especially between 12 noon and 3 pm. Signs of heat stroke: confusion, very high body temperature, "
            "hot dry skin, fainting. Move the person to shade, cool them with water and call 108."
        ),
        keywords=("heat", "summer", "sun", "heatstroke", "temperature", "water", "dehydration"),
    ),
    Document(
        doc_id="documents_help",
        title="Important documents for gig workers and how to keep them",
        category="documents",
        source_name="Unique Identification Authority of India (UIDAI) and DigiLocker",
        source_url="https://uidai.gov.in",
        content=(
            "Key documents: Aadhaar card, Aadhaar-linked mobile number, savings bank account with IFSC code, PAN card, and "
            "your e-Shram UAN card. Riders and drivers also need a driving licence, vehicle RC, valid vehicle insurance "
            "(third-party insurance is compulsory) and a PUC certificate. To update the mobile number in Aadhaar, visit an "
            "Aadhaar Seva Kendra; UIDAI helpline is 1947. Store digital copies safely in DigiLocker at https://digilocker.gov.in. "
            "Never share your Aadhaar OTP with anyone."
        ),
        keywords=("aadhaar", "pan", "licence", "license", "rc", "insurance", "puc", "digilocker", "mobile update", "document", "kyc"),
    ),
)

_BY_ID: dict[str, Document] = {doc.doc_id: doc for doc in DOCUMENTS}


def get_document(doc_id: str) -> Document:
    """Look up a document by id (raises KeyError for unknown ids)."""
    return _BY_ID[doc_id]


HELPLINES: tuple[tuple[str, str], ...] = (
    ("e-Shram helpline (toll-free, 9 languages)", "14434"),
    ("Emergency (police / fire / ambulance)", "112"),
    ("Ambulance", "108"),
    ("Women helpline", "181"),
    ("Ayushman Bharat PM-JAY", "14555"),
    ("Aadhaar (UIDAI)", "1947"),
)

ESHRAM_GUIDE_TEXT = (
    "**Who can register:** age 16-59, not a member of EPFO/ESIC/NPS, unorganised or gig/platform worker.\n\n"
    "**Keep ready:** Aadhaar number, Aadhaar-linked mobile number, savings bank account number with IFSC code.\n\n"
    + "\n".join(f"{i}. {step}" for i, step in enumerate(ESHRAM_STEPS, start=1))
    + "\n\n**Help:** e-Shram helpline 14434 (toll-free, Mon-Sat, 9 languages).\n\n"
    "Source: Ministry of Labour & Employment, https://eshram.gov.in"
)

# Checklist per worker role: (document, why it matters).
_COMMON_DOCS: tuple[tuple[str, str], ...] = (
    ("Aadhaar card", "Identity proof; needed for e-Shram and bank KYC."),
    ("Mobile number linked to Aadhaar", "Receives OTP for e-Shram and DigiLocker."),
    ("Savings bank account + IFSC", "Platform payouts and government benefits (DBT)."),
    ("PAN card", "Bank KYC and income-tax filing."),
    ("e-Shram UAN card", "Access to welfare schemes and PM-JAY health cover."),
)
_VEHICLE_DOCS: tuple[tuple[str, str], ...] = (
    ("Driving licence", "Legally required to ride or drive."),
    ("Vehicle RC (registration certificate)", "Proof of vehicle registration; platforms ask for it."),
    ("Vehicle insurance", "Third-party insurance is compulsory by law."),
    ("PUC certificate", "Pollution certificate required for vehicles on the road."),
)

ROLE_DOCUMENTS: dict[str, tuple[tuple[str, str], ...]] = {
    "delivery": _COMMON_DOCS + _VEHICLE_DOCS,
    "driver": _COMMON_DOCS
    + _VEHICLE_DOCS
    + (("Commercial permit / badge", "Needed for taxis in many states; rules vary by state."),),
    "daily_wage": _COMMON_DOCS
    + (
        ("Construction worker (BOCW) board registration", "If you work in construction, gives welfare board benefits."),
        ("Ration card", "One Nation One Ration Card lets you collect ration in any state."),
    ),
}
