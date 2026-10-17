"""Security headers (strict CSP: no inline scripts, no eval) and a per-request id."""

from __future__ import annotations

import secrets
from typing import Final

from starlette.types import ASGIApp, Message, Receive, Scope, Send

CSP: Final = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data: blob:",
        "font-src 'self'",
        "connect-src 'self'",
        "media-src 'self' blob:",
        "worker-src 'self'",
        "manifest-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    )
)

BASE_HEADERS: Final[tuple[tuple[bytes, bytes], ...]] = (
    (b"content-security-policy", CSP.encode()),
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(self), microphone=(self), geolocation=(self), payment=(), usb=()"),
)
HSTS: Final = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
REQUEST_ID_BYTES: Final = 8


class SecurityHeadersMiddleware:
    """Adds security headers and X-Request-ID to every HTTP response."""

    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        self.app = app
        self.headers = (*BASE_HEADERS, HSTS) if hsts else BASE_HEADERS

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = secrets.token_hex(REQUEST_ID_BYTES)
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(self.headers)
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
