"""Open-Meteo forecast proxy with coordinate rounding (~1 km), TTL cache and fallback."""

from __future__ import annotations

import time
from typing import Any, Final

import httpx
from pydantic import BaseModel, Field

from app.ai.fallback import LRUCache
from app.constants import (
    WEATHER_CACHE_SECONDS,
    WEATHER_CACHE_SIZE,
    WEATHER_COORD_DECIMALS,
    WEATHER_FORECAST_HOURS,
    WEATHER_TIMEOUT_SECONDS,
)
from app.logs import log_event

OPEN_METEO_URL: Final = "https://api.open-meteo.com/v1/forecast"
TIME_LABEL_SLICE: Final = slice(11, 16)  # "2026-10-17T14:00" -> "14:00"


class WeatherRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class WeatherHour(BaseModel):
    time: str
    temp_c: float | None
    feels_like_c: float | None
    rain_probability: int | None


class WeatherOut(BaseModel):
    available: bool
    rain_probability_max: int = 0
    rain_time: str | None = None
    apparent_max_c: float | None = None
    heat_caution_c: float
    heat_danger_c: float
    hours: list[WeatherHour] = Field(default_factory=list)


def _column(hourly: dict[str, Any], key: str) -> list[Any]:
    values = hourly.get(key) or []
    return list(values)[:WEATHER_FORECAST_HOURS]


def parse_forecast(payload: dict[str, Any], caution: float, danger: float) -> WeatherOut:
    """Turn Open-Meteo hourly arrays into a compact summary."""
    hourly = payload.get("hourly") or {}
    times = _column(hourly, "time")
    temps = _column(hourly, "temperature_2m")
    feels = _column(hourly, "apparent_temperature")
    rain = _column(hourly, "precipitation_probability")
    hours = [
        WeatherHour(
            time=str(t)[TIME_LABEL_SLICE],
            temp_c=temps[i] if i < len(temps) else None,
            feels_like_c=feels[i] if i < len(feels) else None,
            rain_probability=rain[i] if i < len(rain) else None,
        )
        for i, t in enumerate(times)
    ]
    rainy = [h for h in hours if h.rain_probability is not None]
    wettest = max(rainy, key=lambda h: h.rain_probability or 0, default=None)
    feels_known = [h.feels_like_c for h in hours if h.feels_like_c is not None]
    return WeatherOut(
        available=bool(hours),
        rain_probability_max=wettest.rain_probability or 0 if wettest else 0,
        rain_time=wettest.time if wettest else None,
        apparent_max_c=max(feels_known) if feels_known else None,
        heat_caution_c=caution,
        heat_danger_c=danger,
        hours=hours,
    )


class WeatherService:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http
        self._cache: LRUCache[tuple[float, float], tuple[float, WeatherOut]] = LRUCache(WEATHER_CACHE_SIZE)

    async def forecast(self, req: WeatherRequest, caution: float, danger: float) -> tuple[WeatherOut, str | None]:
        """Return (forecast, failure_reason). Failures return an empty, honest result."""
        key = (round(req.lat, WEATHER_COORD_DECIMALS), round(req.lon, WEATHER_COORD_DECIMALS))
        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < WEATHER_CACHE_SECONDS:
            return cached[1], None
        params: dict[str, str | float | int] = {
            "latitude": key[0],
            "longitude": key[1],
            "hourly": "temperature_2m,apparent_temperature,precipitation_probability",
            "forecast_hours": WEATHER_FORECAST_HOURS,
            "timezone": "auto",
        }
        try:
            response = await self._http.get(OPEN_METEO_URL, params=params, timeout=WEATHER_TIMEOUT_SECONDS)
            response.raise_for_status()
            result = parse_forecast(response.json(), caution, danger)
        except (httpx.HTTPError, ValueError) as exc:
            reason = "timeout" if isinstance(exc, httpx.TimeoutException) else "weather_unavailable"
            log_event("weather_failure", reason=reason)
            return WeatherOut(available=False, heat_caution_c=caution, heat_danger_c=danger), reason
        self._cache.put(key, (time.monotonic(), result))
        return result, None
