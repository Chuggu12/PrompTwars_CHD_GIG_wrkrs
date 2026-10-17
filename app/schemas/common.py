"""Shared response envelope and error body."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Engine = Literal["gemini", "deterministic"]


class Meta(BaseModel):
    """How a response was produced. degraded=True means the AI path was not used."""

    engine: Engine
    degraded: bool
    reason: str | None = None
    model: str | None = None
    request_id: str


class Envelope[T](BaseModel):
    data: T
    meta: Meta


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None
