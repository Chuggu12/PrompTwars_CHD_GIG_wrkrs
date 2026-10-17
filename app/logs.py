"""Structured JSON logging. Callers pass only non-personal fields; never user text or bodies."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

_LOGGER = logging.getLogger("rozi")


def configure_logging(level: int = logging.INFO) -> None:
    """Send app logs to stderr as one JSON object per line."""
    if not _LOGGER.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        _LOGGER.addHandler(handler)
    _LOGGER.setLevel(level)
    _LOGGER.propagate = False


def log_event(event: str, level: int = logging.INFO, **fields: str | int | float | bool | None) -> None:
    """Emit {"ts", "event", ...fields} as JSON."""
    record = {"ts": datetime.now(UTC).isoformat(timespec="seconds"), "event": event, **fields}
    _LOGGER.log(level, json.dumps(record, ensure_ascii=False, default=str))
