"""Gemini REST client (plain httpx) with failover across the model chain.

Every call returns AIResult: either validated data or a typed FailureReason. The API key
travels only in the x-goog-api-key header, never in the URL. Logs carry the model and
failure reason only, never prompt or response text.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.constants import AI_MAX_OUTPUT_TOKENS, AI_TIMEOUT_SECONDS

from .registry import FailureReason, ModelRegistry

FAILOVER_REASONS = frozenset(
    {
        FailureReason.MODEL_NOT_FOUND,
        FailureReason.QUOTA,
        FailureReason.TIMEOUT,
        FailureReason.SERVER_ERROR,
        FailureReason.BAD_REQUEST,
    }
)
_KEEP_SCHEMA_KEYS = frozenset(
    {"type", "description", "enum", "items", "properties", "required", "minItems", "maxItems"}
)


@dataclass(frozen=True)
class AIResult[M: BaseModel]:
    data: M | None
    model: str | None
    reason: FailureReason | None

    @property
    def ok(self) -> bool:
        return self.data is not None


@dataclass(frozen=True)
class ImagePart:
    mime_type: str
    data: bytes


def gemini_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Convert a Pydantic JSON schema into Gemini's OpenAPI-subset responseSchema."""
    raw = model.model_json_schema()
    defs = raw.get("$defs", {})

    def convert(node: dict[str, Any]) -> dict[str, Any]:
        if "$ref" in node:
            return convert(defs[node["$ref"].split("/")[-1]])
        if "anyOf" in node:
            options = [o for o in node["anyOf"] if o.get("type") != "null"]
            nullable: dict[str, Any] = convert(options[0]) if options else {"type": "STRING"}
            nullable["nullable"] = True
            return nullable
        if "const" in node:
            node = {**node, "enum": [node["const"]], "type": "string"}
        out: dict[str, Any] = {k: v for k, v in node.items() if k in _KEEP_SCHEMA_KEYS}
        if "type" in out:
            out["type"] = str(out["type"]).upper()
        if "properties" in out:
            out["properties"] = {k: convert(v) for k, v in out["properties"].items()}
        if "items" in out:
            out["items"] = convert(out["items"])
        return out

    return convert(raw)


def _status_reason(status: int) -> FailureReason:
    if status == 404:
        return FailureReason.MODEL_NOT_FOUND
    if status == 429:
        return FailureReason.QUOTA
    if status in (401, 403):
        return FailureReason.AUTH
    if status == 400:
        return FailureReason.BAD_REQUEST
    return FailureReason.SERVER_ERROR


def _response_text(payload: dict[str, Any]) -> str | None:
    """Joined non-thought text parts of the first candidate, or None if blocked/empty."""
    candidates = payload.get("candidates") or []
    if not candidates:
        return None
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return text or None


class GeminiClient:
    """Schema-constrained JSON generation with model failover and one retry on bad JSON."""

    def __init__(self, settings: Settings, registry: ModelRegistry, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._registry = registry
        self._http = http

    @property
    def registry(self) -> ModelRegistry:
        return self._registry

    def _body(
        self, prompt: str, system: str, schema: type[BaseModel], temperature: float, image: ImagePart | None
    ) -> dict[str, Any]:
        parts: list[dict[str, Any]] = [{"text": prompt}]
        if image is not None:
            parts.append(
                {"inline_data": {"mime_type": image.mime_type, "data": base64.b64encode(image.data).decode("ascii")}}
            )
        return {
            "contents": [{"role": "user", "parts": parts}],
            "systemInstruction": {"parts": [{"text": system}]},
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": AI_MAX_OUTPUT_TOKENS,
                "responseMimeType": "application/json",
                "responseSchema": gemini_schema(schema),
            },
        }

    async def _post(self, model: str, body: dict[str, Any], key: str) -> tuple[str | None, FailureReason | None]:
        try:
            response = await self._http.post(
                f"{self._settings.gemini_base_url}/models/{model}:generateContent",
                json=body,
                headers={"x-goog-api-key": key},
                timeout=AI_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException:
            return None, FailureReason.TIMEOUT
        except httpx.HTTPError:
            return None, FailureReason.SERVER_ERROR
        if response.status_code != 200:
            return None, _status_reason(response.status_code)
        try:
            text = _response_text(response.json())
        except ValueError:
            return None, FailureReason.SERVER_ERROR
        return (text, None) if text else (None, FailureReason.BLOCKED)

    @staticmethod
    def _parse[M: BaseModel](text: str, schema: type[M]) -> M | None:
        try:
            return schema.model_validate(json.loads(text))
        except (ValueError, ValidationError):
            return None

    async def _try_model[M: BaseModel](
        self, model: str, body: dict[str, Any], schema: type[M], key: str
    ) -> AIResult[M]:
        """One model: call, validate, retry once on invalid JSON."""
        reason: FailureReason | None = None
        for _attempt in range(2):
            text, reason = await self._post(model, body, key)
            if text is None:
                return AIResult(None, model, reason)
            parsed = self._parse(text, schema)
            if parsed is not None:
                return AIResult(parsed, model, None)
            reason = FailureReason.BAD_JSON
        return AIResult(None, model, reason)

    async def generate[M: BaseModel](
        self,
        prompt: str,
        schema: type[M],
        *,
        system: str,
        temperature: float = 0.2,
        image: ImagePart | None = None,
    ) -> AIResult[M]:
        """Try each available model in order; fail over on transient/model errors."""
        key = self._settings.api_key
        if not key:
            return AIResult(None, None, FailureReason.NO_KEY)
        models = self._registry.available()
        if not models:
            return AIResult(None, None, FailureReason.NO_MODEL)
        body = self._body(prompt, system, schema, temperature, image)
        result: AIResult[M] = AIResult(None, None, FailureReason.NO_MODEL)
        for model in models:
            result = await self._try_model(model, body, schema, key)
            if result.ok:
                return result
            reason = result.reason or FailureReason.SERVER_ERROR
            self._registry.record_failure(model, reason)
            if reason not in FAILOVER_REASONS:
                return result
        return result
