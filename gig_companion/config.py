"""Central configuration: environment settings, supported languages and worker roles."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# ISO 639-1 code -> English name (used inside prompts for translation).
LANGUAGES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "kn": "Kannada",
    "gu": "Gujarati",
}

# Native-script labels shown in the language picker.
LANGUAGE_LABELS: dict[str, str] = {
    "en": "English",
    "hi": "हिन्दी (Hindi)",
    "bn": "বাংলা (Bengali)",
    "ta": "தமிழ் (Tamil)",
    "te": "తెలుగు (Telugu)",
    "mr": "मराठी (Marathi)",
    "kn": "ಕನ್ನಡ (Kannada)",
    "gu": "ગુજરાતી (Gujarati)",
}

ROLES: dict[str, str] = {
    "delivery": "Delivery partner",
    "driver": "Driver (cab / bike taxi / auto)",
    "daily_wage": "Daily-wage worker",
}


def language_name(code: str) -> str:
    """Return the English name for a language code, defaulting to English."""
    return LANGUAGES.get(code, "English")


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Read once from the environment; immutable afterwards."""

    gemini_api_key: str | None
    model_name: str
    max_input_chars: int = 1500
    rag_top_k: int = 3
    # Minimum IDF-weighted query-term coverage for an answer to count as grounded.
    rag_confidence_threshold: float = 0.4
    max_output_tokens: int = 1024


def get_settings() -> Settings:
    """Build settings from environment variables (see .env.example)."""
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        # Gemini 1.5 Flash is retired; 2.5 Flash is the current low-latency tier.
        model_name=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    )
