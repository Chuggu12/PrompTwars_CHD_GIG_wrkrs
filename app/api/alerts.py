"""Stateless alert evaluation. The browser keeps history, caps and quiet hours."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.domain.alerts import Alert, AlertContext, WeatherSignal, evaluate

from .deps import StoreDep

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class WeatherIn(BaseModel):
    rain_probability_max: int = Field(ge=0, le=100)
    rain_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    apparent_max_c: Decimal | None = Field(default=None, ge=-50, le=70)


class AlertRequest(BaseModel):
    context: AlertContext
    weather: WeatherIn | None = None


@router.post("/evaluate")
def evaluate_alerts(req: AlertRequest, store: StoreDep) -> list[Alert]:
    caution, danger = store.heat_thresholds()
    weather = (
        WeatherSignal(
            **req.weather.model_dump(), heat_caution_c=Decimal(str(caution)), heat_danger_c=Decimal(str(danger))
        )
        if req.weather
        else None
    )
    ctx = req.context.model_copy(
        update={"weather": weather, "data_needs_verification": store.any_needs_verification(req.context.now.date())}
    )
    return evaluate(ctx, store.alert_copy)
