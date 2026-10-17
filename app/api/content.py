"""Verified content from app/data, localised, with freshness flags."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.domain.constants import Lang
from app.schemas.content import ContentResponse

from .deps import StoreDep

router = APIRouter(prefix="/api/content", tags=["content"])

ContentName = Literal["welfare-schemes", "helplines", "state-boards", "legal-refs", "heat-thresholds"]
CACHE_HEADER = "public, max-age=3600"


class ContentMeta(BaseModel):
    needs_verification: bool
    files: list[str]


@router.get("/meta")
def content_meta(store: StoreDep) -> ContentMeta:
    return ContentMeta(needs_verification=store.any_needs_verification(date.today()), files=sorted(store.files))


@router.get("/{name}")
def content(name: ContentName, store: StoreDep, response: Response, lang: Lang = "en") -> ContentResponse:
    response.headers["cache-control"] = CACHE_HEADER
    return store.localized(name, lang, date.today())
