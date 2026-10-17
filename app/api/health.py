"""Liveness, readiness (model status) and a rate-limited manual model re-check."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.ai.registry import RegistryStatus

from .deps import RegistryDep, SettingsDep

router = APIRouter(prefix="/api/health", tags=["health"])


class Liveness(BaseModel):
    status: str
    version: str


class Readiness(BaseModel):
    status: str
    version: str
    models: RegistryStatus
    reports_enabled: bool
    report_quorum: int
    auto_apply: str


class RecheckResult(BaseModel):
    ran: bool
    models: RegistryStatus


@router.get("")
def liveness() -> Liveness:
    return Liveness(status="ok", version=__version__)


@router.get("/models")
def readiness(registry: RegistryDep, settings: SettingsDep) -> Readiness:
    status = registry.status()
    return Readiness(
        status="ok" if status.mode == "gemini" else "degraded",
        version=__version__,
        models=status,
        reports_enabled=settings.github_enabled,
        report_quorum=settings.report_quorum,
        auto_apply=settings.auto_apply,
    )


@router.post("/models/recheck")
async def recheck(registry: RegistryDep) -> RecheckResult:
    ran = await registry.recheck()
    return RecheckResult(ran=ran, models=registry.status())
