"""Model registry: which models from MODEL_CHAIN are actually available right now.

Refreshed at startup and every MODEL_REFRESH_SECONDS via the Gemini models-list
endpoint. Models that fail with model_not_found are skipped until the next refresh;
if none are available the app runs in deterministic mode.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

import httpx
from pydantic import BaseModel

from app.config import Settings
from app.constants import AI_TIMEOUT_SECONDS, MODEL_RECHECK_MIN_SECONDS
from app.logs import log_event

MODELS_PAGE_SIZE = 1000
QUOTA_COOLDOWN_SECONDS = 60


class FailureReason(StrEnum):
    NO_KEY = "no_key"
    NO_MODEL = "no_model"
    MODEL_NOT_FOUND = "model_not_found"
    QUOTA = "quota"
    TIMEOUT = "timeout"
    BAD_JSON = "bad_json"
    SERVER_ERROR = "server_error"
    BAD_REQUEST = "bad_request"
    AUTH = "auth"
    BLOCKED = "blocked"


class RegistryStatus(BaseModel):
    mode: Literal["gemini", "deterministic"]
    has_key: bool
    configured: list[str]
    available: list[str]
    active: str | None
    last_check: datetime | None
    last_failure_reason: str | None
    last_failure_at: datetime | None


class ModelRegistry:
    """Tracks model availability. All state is non-personal."""

    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http
        self._available: list[str] = []
        self._cooldown_until: dict[str, float] = {}
        self._last_check: datetime | None = None
        self._last_check_mono = 0.0
        self._last_failure: tuple[str, datetime] | None = None

    @property
    def has_key(self) -> bool:
        return bool(self._settings.api_key)

    def available(self) -> list[str]:
        """Models to try, in chain order, skipping ones cooling down after quota errors."""
        now = time.monotonic()
        return [m for m in self._available if self._cooldown_until.get(m, 0.0) <= now]

    async def refresh(self) -> None:
        """Ask Gemini which models exist and keep the configured ones that do."""
        self._last_check = datetime.now(UTC)
        self._last_check_mono = time.monotonic()
        key = self._settings.api_key
        if not key:
            self._available = []
            self.record_failure(None, FailureReason.NO_KEY)
            return
        try:
            response = await self._http.get(
                f"{self._settings.gemini_base_url}/models",
                params={"pageSize": MODELS_PAGE_SIZE},
                headers={"x-goog-api-key": key},
                timeout=AI_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException:
            self._optimistic(FailureReason.TIMEOUT)
            return
        except httpx.HTTPError:
            self._optimistic(FailureReason.SERVER_ERROR)
            return
        if response.status_code in (401, 403):
            self._available = []
            self.record_failure(None, FailureReason.AUTH)
            return
        if response.status_code != 200:
            self._optimistic(FailureReason.SERVER_ERROR)
            return
        listed = {str(m.get("name", "")).removeprefix("models/") for m in response.json().get("models", [])}
        self._available = [m for m in self._settings.models if m in listed]
        self._cooldown_until.clear()
        if not self._available:
            self.record_failure(None, FailureReason.NO_MODEL)
        log_event("models_refreshed", available=",".join(self._available) or "none")

    def _optimistic(self, reason: FailureReason) -> None:
        """Listing failed for a transient reason: keep trying the configured chain."""
        self._available = list(self._settings.models)
        self.record_failure(None, reason)

    async def recheck(self) -> bool:
        """Rate-limited manual refresh (Fix-It recheck_ai_models). Returns True if it ran."""
        if time.monotonic() - self._last_check_mono < MODEL_RECHECK_MIN_SECONDS:
            return False
        await self.refresh()
        return True

    def record_failure(self, model: str | None, reason: FailureReason) -> None:
        self._last_failure = (reason.value, datetime.now(UTC))
        if model and reason is FailureReason.MODEL_NOT_FOUND and model in self._available:
            self._available.remove(model)
        if model and reason is FailureReason.QUOTA:
            self._cooldown_until[model] = time.monotonic() + QUOTA_COOLDOWN_SECONDS
        log_event("ai_failure", model=model, reason=reason.value)

    def status(self) -> RegistryStatus:
        available = self.available()
        return RegistryStatus(
            mode="gemini" if available else "deterministic",
            has_key=self.has_key,
            configured=list(self._settings.models),
            available=available,
            active=available[0] if available else None,
            last_check=self._last_check,
            last_failure_reason=self._last_failure[0] if self._last_failure else None,
            last_failure_at=self._last_failure[1] if self._last_failure else None,
        )
