"""Weather for rain and heat alerts. POST so coordinates never appear in access logs."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.common import Envelope, Meta
from app.weather import WeatherOut, WeatherRequest

from .deps import RequestIdDep, StoreDep, WeatherDep

router = APIRouter(prefix="/api", tags=["weather"])


@router.post("/weather")
async def weather(req: WeatherRequest, service: WeatherDep, store: StoreDep, rid: RequestIdDep) -> Envelope[WeatherOut]:
    caution, danger = store.heat_thresholds()
    result, failure = await service.forecast(req, caution, danger)
    meta = Meta(engine="deterministic", degraded=failure is not None, reason=failure, request_id=rid)
    return Envelope(data=result, meta=meta)
