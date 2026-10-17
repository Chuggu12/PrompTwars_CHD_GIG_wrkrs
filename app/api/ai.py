"""One endpoint per AI feature. Every response is an Envelope with honest meta."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.ai.client import ImagePart
from app.ai.schemas import (
    ContractExplanation,
    DayGist,
    DayGistRequest,
    GrievanceDraft,
    GrievanceExtractRequest,
    LetterText,
    PolishRequest,
    SimplifyRequest,
    TextOut,
    TranslateRequest,
    WelfareSummary,
    WelfareSummaryRequest,
)
from app.constants import IMAGE_SIGNATURES, MAX_UPLOAD_BYTES
from app.domain.constants import Lang
from app.schemas.common import Envelope

from .deps import AIDep, RequestIdDep

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/translate")
async def translate(req: TranslateRequest, ai: AIDep, rid: RequestIdDep) -> Envelope[TextOut]:
    return await ai.translate(req, rid)


@router.post("/simplify")
async def simplify(req: SimplifyRequest, ai: AIDep, rid: RequestIdDep) -> Envelope[TextOut]:
    return await ai.simplify(req, rid)


@router.post("/grievance/extract")
async def grievance_extract(req: GrievanceExtractRequest, ai: AIDep, rid: RequestIdDep) -> Envelope[GrievanceDraft]:
    return await ai.extract_grievance(req, rid)


@router.post("/grievance/polish")
async def grievance_polish(req: PolishRequest, ai: AIDep, rid: RequestIdDep) -> Envelope[LetterText]:
    return await ai.polish_letter(req, rid)


@router.post("/welfare/summary")
async def welfare_summary(req: WelfareSummaryRequest, ai: AIDep, rid: RequestIdDep) -> Envelope[WelfareSummary]:
    try:
        return await ai.welfare_summary(req, rid)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="unknown_scheme") from exc


@router.post("/daygist")
async def day_gist(req: DayGistRequest, ai: AIDep, rid: RequestIdDep) -> Envelope[DayGist]:
    return await ai.day_gist(req, rid)


def detect_image_type(data: bytes) -> str | None:
    """Trust magic bytes, not the client-declared content type."""
    for mime, signature in IMAGE_SIGNATURES.items():
        if data.startswith(signature) and (mime != "image/webp" or data[8:12] == b"WEBP"):
            return mime
    return None


@router.post("/contract")
async def contract(
    ai: AIDep,
    rid: RequestIdDep,
    file: Annotated[UploadFile, File()],
    lang: Annotated[Lang, Form()] = "en",
    consent: Annotated[bool, Form()] = False,
) -> Envelope[ContractExplanation]:
    """Explain the 3 key clauses of a screenshot. The image is held in memory only."""
    if not consent:
        raise HTTPException(status_code=400, detail="consent_required")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="too_large")
    mime = detect_image_type(data)
    if mime is None:
        raise HTTPException(status_code=415, detail="unsupported_image")
    return await ai.explain_contract(ImagePart(mime_type=mime, data=data), lang, rid)
