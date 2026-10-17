"""Application factory: middleware, lifespan services, routers, pages and error handlers."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.ai.client import GeminiClient
from app.ai.registry import ModelRegistry
from app.ai.service import AIService
from app.api import ai, alerts, content, domain, health, report, selfheal, weather
from app.config import Settings, get_settings
from app.constants import APP_NAME, MODEL_REFRESH_SECONDS
from app.content import ContentStore
from app.logs import configure_logging, log_event
from app.reports import ReportService
from app.security.bodylimit import BodySizeLimitMiddleware
from app.security.headers import SecurityHeadersMiddleware
from app.security.ratelimit import RateLimiter, RateLimitMiddleware
from app.weather import WeatherService

BASE_DIR: Final = Path(__file__).parent
STATIC_DIR: Final = BASE_DIR / "static"
GZIP_MIN_BYTES: Final = 1024
NO_CACHE: Final = {"cache-control": "no-cache"}


async def _refresh_models_forever(registry: ModelRegistry) -> None:
    while True:
        await asyncio.sleep(MODEL_REFRESH_SECONDS)
        await registry.refresh()


def _lifespan(settings: Settings, transport: httpx.AsyncBaseTransport | None):  # type: ignore[no-untyped-def]
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient(transport=transport, follow_redirects=False) as http:
            registry = ModelRegistry(settings, http)
            store = ContentStore()
            app.state.settings = settings
            app.state.http = http
            app.state.store = store
            app.state.registry = registry
            app.state.ai = AIService(GeminiClient(settings, registry, http), store)
            app.state.weather = WeatherService(http)
            app.state.reports = ReportService(settings, http)
            await registry.refresh()
            task = asyncio.create_task(_refresh_models_forever(registry))
            log_event("startup", version=__version__, mode=registry.status().mode)
            try:
                yield
            finally:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    return lifespan


def _error(status: int, code: str, message: str, request: Request, fields: list[str] | None = None) -> JSONResponse:
    """Error body without echoing user input (validation details list field names only)."""
    rid = getattr(request.state, "request_id", None)
    body: dict[str, object] = {"code": code, "message": message, "request_id": rid}
    if fields:
        body["fields"] = fields
    return JSONResponse(status_code=status, content={"error": body})


def _register_errors(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = sorted({".".join(str(p) for p in err.get("loc", ())[1:]) for err in exc.errors()})
        return _error(422, "invalid_input", "Some details are not valid. Please check and try again.", request, fields)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return _error(exc.status_code, str(exc.detail), str(exc.detail), request)

    @app.exception_handler(ValueError)
    async def domain_error(request: Request, _exc: ValueError) -> JSONResponse:
        return _error(422, "invalid_input", "These numbers do not add up. Please check them.", request)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        log_event("unhandled_error", error=type(exc).__name__, path=request.url.path)
        return _error(500, "internal_error", "Something went wrong on our side.", request)


def _register_pages(app: FastAPI) -> None:
    templates = Jinja2Templates(directory=BASE_DIR / "templates")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def shell(request: Request) -> Response:
        return templates.TemplateResponse(
            request, "shell.html", {"app_name": APP_NAME, "version": __version__}, headers=NO_CACHE
        )

    @app.get("/offline.html", response_class=HTMLResponse, include_in_schema=False)
    def offline(request: Request) -> Response:
        return templates.TemplateResponse(request, "offline.html", {"app_name": APP_NAME})

    @app.get("/sw.js", include_in_schema=False)
    def service_worker() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "sw.js", media_type="text/javascript", headers={**NO_CACHE, "service-worker-allowed": "/"}
        )

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest() -> FileResponse:
        return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(STATIC_DIR / "icons" / "icon.svg", media_type="image/svg+xml")


def create_app(settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    """Build the FastAPI app. `transport` lets tests mock all outbound HTTP."""
    settings = settings or get_settings()
    configure_logging()
    is_prod = settings.env == "production"
    app = FastAPI(
        title=APP_NAME,
        version=__version__,
        lifespan=_lifespan(settings, transport),
        docs_url=None if is_prod else "/api/docs",
        redoc_url=None,
        openapi_url=None if is_prod else "/api/openapi.json",
    )
    app.add_middleware(GZipMiddleware, minimum_size=GZIP_MIN_BYTES)
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(RateLimitMiddleware, limiter=RateLimiter(), trust_proxy=settings.trust_proxy)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.hosts)
    app.add_middleware(SecurityHeadersMiddleware, hsts=is_prod)

    for module in (health, domain, ai, alerts, content, weather, selfheal, report):
        app.include_router(module.router)
    _register_errors(app)
    _register_pages(app)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
