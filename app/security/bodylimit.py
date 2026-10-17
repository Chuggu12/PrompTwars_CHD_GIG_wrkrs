"""Rejects request bodies above a per-route size limit (checked on headers and stream)."""

from __future__ import annotations

import json
from typing import Final

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.constants import MAX_JSON_BODY_BYTES, UPLOAD_ENVELOPE_BYTES

UPLOAD_PATHS: Final = ("/api/ai/contract",)


class BodyTooLargeError(Exception):
    """Raised from the wrapped receive() when the stream exceeds the limit."""


def limit_for(path: str) -> int:
    return UPLOAD_ENVELOPE_BYTES if path.startswith(UPLOAD_PATHS) else MAX_JSON_BODY_BYTES


async def _reject(send: Send) -> None:
    body = json.dumps({"error": {"code": "too_large", "message": "Request is too large."}}).encode()
    await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": body})


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = limit_for(scope.get("path", ""))
        for name, value in scope.get("headers", []):
            if name == b"content-length" and value.isdigit() and int(value) > limit:
                await _reject(send)
                return
        received = 0
        started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise BodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except BodyTooLargeError:
            if not started:
                await _reject(send)
