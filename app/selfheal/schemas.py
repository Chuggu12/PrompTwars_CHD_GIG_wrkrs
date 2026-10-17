"""Fix-It schemas. Categories and action ids are closed enums shared with the AI schema,
so neither the AI nor a crafted request can name anything outside the whitelist."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from app.constants import MAX_REPORT_CHARS
from app.domain.constants import Lang


class Category(StrEnum):
    ALERTS_NOISY = "ALERTS_NOISY"
    TEXT_READABILITY = "TEXT_READABILITY"
    LANGUAGE = "LANGUAGE"
    VOICE_INPUT = "VOICE_INPUT"
    WRONG_NUMBER = "WRONG_NUMBER"
    PERFORMANCE = "PERFORMANCE"
    FEATURE_BROKEN = "FEATURE_BROKEN"
    STORAGE_CORRUPT = "STORAGE_CORRUPT"
    DATA_OUTDATED = "DATA_OUTDATED"
    ACCESSIBILITY_OTHER = "ACCESSIBILITY_OTHER"
    FEATURE_REQUEST = "FEATURE_REQUEST"
    OTHER = "OTHER"


class ActionId(StrEnum):
    SET_FONT_SCALE = "set_font_scale"
    SET_HIGH_CONTRAST = "set_high_contrast"
    SET_LANGUAGE = "set_language"
    SET_READING_LEVEL = "set_reading_level"
    SET_READ_ALOUD_DEFAULT = "set_read_aloud_default"
    REDUCE_ALERT_FREQUENCY = "reduce_alert_frequency"
    MUTE_ALERT_TYPE = "mute_alert_type"
    ENABLE_QUIET_MODE = "enable_quiet_mode"
    ENABLE_LITE_MODE = "enable_lite_mode"
    SWITCH_TO_MANUAL_ENTRY = "switch_to_manual_entry"
    CLEAR_UI_CACHE_AND_RELOAD = "clear_ui_cache_and_reload"
    RESET_VIEW_STATE = "reset_view_state"
    REFRESH_DATA_FILES = "refresh_data_files"
    RECHECK_AI_MODELS = "recheck_ai_models"
    RECALC_AND_EXPLAIN = "recalc_and_explain"
    REPAIR_STORAGE = "repair_storage"
    OPEN_HUMAN_HELP = "open_human_help"
    SUBMIT_REPORT = "submit_report"


Severity = Literal["low", "medium", "high"]
Risk = Literal["safe", "confirm"]
ParamValue = str | int | float | bool | None


class TriageCategory(BaseModel):
    severity: Severity
    actions: list[ActionId]
    keywords: dict[Lang, list[str]]
    message: dict[Lang, str]


class TriageBook(BaseModel):
    categories: dict[Category, TriageCategory]
    alert_type_words: dict[str, list[str]] = Field(default_factory=dict)
    clarify_chips: list[Category]


class TriageContext(BaseModel):
    """Non-personal client state that helps triage. No user data."""

    lang: Lang = "en"
    route: str = Field(default="home", pattern=r"^[a-z_-]{1,30}$")
    font_scale: float = Field(default=1.0, ge=1.0, le=1.6)
    alert_cap: int = Field(default=3, ge=0, le=3)
    today: date | None = None
    recent_error_codes: list[str] = Field(default_factory=list, max_length=10)
    last_failed_module: str | None = Field(default=None, pattern=r"^[a-z_-]{1,30}$")
    ai_status: Literal["ok", "degraded", "unknown"] = "unknown"


class TriageRequest(BaseModel):
    text: str = Field(default="", max_length=MAX_REPORT_CHARS * 2)
    chosen_category: Category | None = None
    context: TriageContext = Field(default_factory=TriageContext)


class ProposedAction(BaseModel):
    action_id: ActionId
    params: dict[str, ParamValue] = Field(default_factory=dict)
    risk: Risk


class Clarify(BaseModel):
    question: str
    chips: list[Category]


class Diagnosis(BaseModel):
    category: Category
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    user_message: str
    actions: list[ProposedAction]
    needs_confirmation: bool
    escalate: bool
    clarify: Clarify | None = None


class AIRefinement(BaseModel):
    """What Gemini may return: only enum values and a short message."""

    category: Category
    confidence: float = Field(ge=0, le=1)
    action_ids: list[ActionId] = Field(max_length=3)
    user_message: str = Field(max_length=240)
