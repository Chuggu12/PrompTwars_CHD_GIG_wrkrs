"""Application-wide constants (limits, timeouts, intervals). No magic numbers elsewhere."""

from typing import Final

APP_NAME: Final = "Rozi"

# Request limits.
MAX_JSON_BODY_BYTES: Final = 256 * 1024
MAX_UPLOAD_BYTES: Final = 5 * 1024 * 1024
UPLOAD_ENVELOPE_BYTES: Final = MAX_UPLOAD_BYTES + 64 * 1024
MAX_TEXT_CHARS: Final = 2000
MAX_REPORT_CHARS: Final = 500
MAX_ENTRIES_PER_REQUEST: Final = 2000

# Rate limiting: (requests, window seconds) per client IP and route group.
RATE_LIMIT_DEFAULT: Final = (120, 60)
RATE_LIMIT_AI: Final = (20, 60)
RATE_LIMIT_SELFHEAL: Final = (5, 60)
RATE_LIMIT_REPORT: Final = (5, 60)
RATE_LIMIT_CLEANUP_SECONDS: Final = 60

# AI layer.
AI_TIMEOUT_SECONDS: Final = 15.0
MODEL_REFRESH_SECONDS: Final = 600
MODEL_RECHECK_MIN_SECONDS: Final = 30
AI_CACHE_SIZE: Final = 128
AI_MAX_OUTPUT_TOKENS: Final = 4096  # headroom for models that spend tokens on thinking

# Weather.
WEATHER_CACHE_SECONDS: Final = 900
WEATHER_TIMEOUT_SECONDS: Final = 8.0
WEATHER_COORD_DECIMALS: Final = 2
WEATHER_FORECAST_HOURS: Final = 12
WEATHER_CACHE_SIZE: Final = 256

# Content freshness.
CONTENT_STALE_DAYS: Final = 60

# Accepted image types for the contract helper (magic-byte prefixes).
IMAGE_SIGNATURES: Final[dict[str, bytes]] = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
    "image/webp": b"RIFF",
}
