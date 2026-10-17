"""Dependency accessors for objects created once in the app lifespan."""

from __future__ import annotations

from typing import Annotated, cast

import httpx
from fastapi import Depends, Request

from app.ai.registry import ModelRegistry
from app.ai.service import AIService
from app.config import Settings
from app.content import ContentStore
from app.reports import ReportService
from app.weather import WeatherService


def get_settings_dep(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_store(request: Request) -> ContentStore:
    return cast(ContentStore, request.app.state.store)


def get_ai(request: Request) -> AIService:
    return cast(AIService, request.app.state.ai)


def get_registry(request: Request) -> ModelRegistry:
    return cast(ModelRegistry, request.app.state.registry)


def get_http(request: Request) -> httpx.AsyncClient:
    return cast(httpx.AsyncClient, request.app.state.http)


def get_weather(request: Request) -> WeatherService:
    return cast(WeatherService, request.app.state.weather)


def get_reports(request: Request) -> ReportService:
    return cast(ReportService, request.app.state.reports)


def request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "-"))


StoreDep = Annotated[ContentStore, Depends(get_store)]
AIDep = Annotated[AIService, Depends(get_ai)]
RegistryDep = Annotated[ModelRegistry, Depends(get_registry)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
WeatherDep = Annotated[WeatherService, Depends(get_weather)]
ReportsDep = Annotated[ReportService, Depends(get_reports)]
RequestIdDep = Annotated[str, Depends(request_id)]
