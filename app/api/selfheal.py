"""Fix-It triage (stateless, never stored). Deterministic first, AI refinement if available."""

from __future__ import annotations

from fastapi import APIRouter

from app.constants import MAX_REPORT_CHARS
from app.domain.redaction import sanitize_text
from app.schemas.common import Envelope, Meta
from app.selfheal.schemas import Diagnosis, TriageRequest
from app.selfheal.triage import merge_refinement, triage

from .deps import AIDep, RequestIdDep, StoreDep

router = APIRouter(prefix="/api/selfheal", tags=["selfheal"])


@router.post("/triage")
async def triage_report(req: TriageRequest, store: StoreDep, ai: AIDep, rid: RequestIdDep) -> Envelope[Diagnosis]:
    try:
        text = sanitize_text(req.text, MAX_REPORT_CHARS)
    except ValueError:
        text = ""
    book = store.triage
    base = triage(text, req.context, book, req.chosen_category)
    if req.chosen_category is not None or not text:
        return Envelope(data=base, meta=Meta(engine="deterministic", degraded=False, request_id=rid))
    refined = await ai.refine_triage(text, req.context)
    if refined is None:
        reason = ai.client.registry.status().last_failure_reason
        return Envelope(data=base, meta=Meta(engine="deterministic", degraded=True, reason=reason, request_id=rid))
    diagnosis = merge_refinement(base, refined, req.context, text, book)
    return Envelope(data=diagnosis, meta=Meta(engine="gemini", degraded=False, request_id=rid))
