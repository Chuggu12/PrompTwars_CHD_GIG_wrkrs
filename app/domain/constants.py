"""Business-rule constants. Thresholds that come from official sources live in app/data."""

from decimal import Decimal
from typing import Final, Literal

Lang = Literal["en", "hi", "ta", "pa"]
LANGS: Final[tuple[Lang, ...]] = ("en", "hi", "ta", "pa")

MAX_AMOUNT: Final = Decimal("10000000")  # ₹1 crore: upper bound for any single figure.
MAX_HOURS_PER_DAY: Final = Decimal("24")

# Minimum-wage comparison: state notifications are usually per day; we assume an 8-hour day.
STANDARD_WORKDAY_HOURS: Final = Decimal("8")

# Guardian defaults (user-configurable within the bounds below).
FATIGUE_WARN_HOURS: Final = Decimal("10")
REST_MODE_HOURS: Final = Decimal("12")
REST_DURATION_HOURS: Final = 8
GUARDIAN_MIN_HOURS: Final = Decimal("4")
GUARDIAN_MAX_HOURS: Final = Decimal("16")

# Goals.
GOAL_NEAR_FRACTION: Final = Decimal("0.8")
PERCENT: Final = Decimal("100")

# Fair pay: flag commission more than this many percentage points above the stated rate.
COMMISSION_TOLERANCE_PP: Final = Decimal("1")
WEEKS_PER_YEAR: Final = Decimal("52")
MONTHS_PER_YEAR: Final = Decimal("12")
MAX_EMI_MONTHS: Final = 120
MAX_INTEREST_PCT: Final = Decimal("60")

# Suggested (not legal) escalation steps for a late payment: (step key, days after due date).
ESCALATION_STEPS: Final[tuple[tuple[str, int], ...]] = (
    ("remind_support", 1),
    ("written_complaint", 7),
    ("labour_department", 15),
    ("cpgrams", 30),
)

# Documents.
DOC_SOON_DAYS: Final = 30
DOC_URGENT_DAYS: Final = 7
DOC_REMINDER_OFFSETS: Final[tuple[int, ...]] = (30, 7, 1)

# Financial year starts in April in India.
FY_START_MONTH: Final = 4

# e-Shram basic rule (age band) from the e-Shram portal.
ESHRAM_MIN_AGE: Final = 16
ESHRAM_MAX_AGE: Final = 59

# Best-hours analysis.
BEST_HOURS_MIN_ENTRIES: Final = 3
TIME_BUCKETS: Final[tuple[tuple[str, int, int], ...]] = (
    ("morning", 6, 11),
    ("afternoon", 11, 16),
    ("evening", 16, 21),
    ("night", 21, 30),  # 21:00 to 06:00 next day (hours 0-5 map to 24-29).
)
HOURS_IN_DAY: Final = 24

# Alerts.
RAIN_ALERT_PROBABILITY: Final = 60
ELIGIBILITY_COOLDOWN_MINUTES: Final = 7 * 24 * 60
DAILY_COOLDOWN_MINUTES: Final = 24 * 60
