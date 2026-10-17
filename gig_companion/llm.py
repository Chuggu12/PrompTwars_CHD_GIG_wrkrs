"""Gemini service layer.

All model access goes through `LLMClient.generate`. When no API key is set, or the
API fails, `LLMUnavailableError` is raised and every caller falls back to a
deterministic answer, so the app keeps working offline.
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from typing import Any, Protocol

from .config import Settings
from .security import get_logger

logger = get_logger(__name__)


class LLMUnavailableError(RuntimeError):
    """No usable model response; callers must fall back to deterministic output."""


class LLMClient(Protocol):
    """Minimal interface the rest of the app depends on (easy to fake in tests)."""

    is_online: bool

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.2,
        schema: dict[str, Any] | None = None,
    ) -> str: ...


class OfflineClient:
    """Used when no API key is configured. Always raises, so callers use fallbacks."""

    is_online = False

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.2,
        schema: dict[str, Any] | None = None,
    ) -> str:
        raise LLMUnavailableError("No Gemini API key configured.")


class GeminiClient:
    """Thin wrapper over the `google-genai` SDK with a bounded in-memory response cache."""

    is_online = True

    def __init__(self, api_key: str, model_name: str, max_output_tokens: int = 1024, cache_size: int = 128):
        # Imported lazily so tests and offline mode do not need the SDK.
        from google import genai
        from google.genai import types

        self._types = types
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name
        self._max_output_tokens = max_output_tokens
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._cache_size = cache_size

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.2,
        schema: dict[str, Any] | None = None,
    ) -> str:
        key = self._cache_key(prompt, system, temperature, schema)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]

        config_kwargs: dict[str, Any] = {
            "system_instruction": system or None,
            "temperature": temperature,
            "max_output_tokens": self._max_output_tokens,
        }
        if schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = schema
        if self._model_name.startswith("gemini-2.5-flash"):
            # Disable "thinking" for low latency; these tasks are short and grounded.
            config_kwargs["thinking_config"] = self._types.ThinkingConfig(thinking_budget=0)

        try:
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=self._types.GenerateContentConfig(**config_kwargs),
            )
        except Exception as exc:  # The SDK raises many error types; log the type only, never content.
            logger.warning("Gemini request failed (%s)", type(exc).__name__)
            raise LLMUnavailableError("The AI service is temporarily unavailable.") from exc

        text = (getattr(response, "text", None) or "").strip()
        if not text:
            raise LLMUnavailableError("The AI service returned an empty response.")
        self._store(key, text)
        return text

    @staticmethod
    def _cache_key(prompt: str, system: str, temperature: float, schema: dict[str, Any] | None) -> str:
        payload = json.dumps([prompt, system, temperature, schema], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _store(self, key: str, value: str) -> None:
        self._cache[key] = value
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)


def build_llm_client(settings: Settings) -> LLMClient:
    """Return a Gemini client when configured, otherwise the offline client."""
    if not settings.gemini_api_key:
        return OfflineClient()
    try:
        return GeminiClient(settings.gemini_api_key, settings.model_name, settings.max_output_tokens)
    except Exception as exc:  # Missing SDK or invalid configuration.
        logger.warning("Gemini client unavailable (%s); running offline.", type(exc).__name__)
        return OfflineClient()
