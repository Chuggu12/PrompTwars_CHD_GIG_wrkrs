"""AI features. Each one: sanitise + redact input, call Gemini with a response schema,
guard the output, and fall back to a deterministic answer with an honest envelope."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

from app.constants import AI_CACHE_SIZE, MAX_REPORT_CHARS, MAX_TEXT_CHARS
from app.content import ContentStore, localize
from app.domain.constants import MAX_AMOUNT, Lang
from app.domain.letters import GrievanceFacts
from app.domain.redaction import redact_pii, sanitize_text
from app.schemas.common import Envelope, Meta
from app.selfheal.schemas import ActionId, AIRefinement, Category, TriageContext

from . import prompts
from .client import AIResult, GeminiClient, ImagePart
from .fallback import LRUCache, adds_facts, extract_day_gist, extract_grievance, fact_tokens, keeps_facts
from .schemas import (
    Clause,
    ContractExplanation,
    DayGist,
    DayGistRequest,
    GrievanceAIOut,
    GrievanceDraft,
    GrievanceExtractRequest,
    LetterText,
    PolishRequest,
    SimplifyRequest,
    TextOut,
    TranslateRequest,
    WelfareAIOut,
    WelfareSummary,
    WelfareSummaryRequest,
)

GUARD_REJECTED = "guard_rejected"
CONTENT_FILE = "welfare-schemes"


def _meta(request_id: str, result: AIResult[BaseModel] | None = None, reason: str | None = None) -> Meta:
    if result is not None and result.ok:
        return Meta(engine="gemini", degraded=False, model=result.model, request_id=request_id)
    failure = reason or (result.reason.value if result and result.reason else None)
    return Meta(engine="deterministic", degraded=True, reason=failure, request_id=request_id)


def _language(lang: Lang) -> str:
    return prompts.LANGUAGE_NAMES[lang]


class AIService:
    """Feature-level AI operations with fallbacks. Stateless apart from a small LRU."""

    def __init__(self, client: GeminiClient, store: ContentStore) -> None:
        self._client = client
        self._store = store
        self._welfare_cache: LRUCache[tuple[str, str, str], WelfareSummary] = LRUCache(AI_CACHE_SIZE)

    @property
    def client(self) -> GeminiClient:
        return self._client

    async def translate(self, req: TranslateRequest, request_id: str) -> Envelope[TextOut]:
        text = sanitize_text(req.text, MAX_TEXT_CHARS * 2)
        if req.source == req.target:
            meta = Meta(engine="deterministic", degraded=False, request_id=request_id)
            return Envelope(data=TextOut(text=text), meta=meta)
        prompt = prompts.TRANSLATE.format(target=_language(req.target), guard=prompts.GUARD, text=text)
        result = await self._client.generate(prompt, TextOut, system=prompts.SYSTEM_BASE, temperature=0.0)
        if result.data is not None and keeps_facts(text, result.data.text):
            return Envelope(data=result.data, meta=_meta(request_id, result))
        reason = GUARD_REJECTED if result.ok else None
        return Envelope(data=TextOut(text=text), meta=_meta(request_id, result, reason))

    async def simplify(self, req: SimplifyRequest, request_id: str) -> Envelope[TextOut]:
        text = sanitize_text(req.text, MAX_TEXT_CHARS)
        prompt = prompts.SIMPLIFY.format(language=_language(req.lang), guard=prompts.GUARD, text=text)
        result = await self._client.generate(prompt, TextOut, system=prompts.SYSTEM_BASE)
        if result.data is not None and not adds_facts(text, result.data.text):
            return Envelope(data=result.data, meta=_meta(request_id, result))
        reason = GUARD_REJECTED if result.ok else None
        return Envelope(data=TextOut(text=text), meta=_meta(request_id, result, reason))

    async def extract_grievance(self, req: GrievanceExtractRequest, request_id: str) -> Envelope[GrievanceDraft]:
        text = sanitize_text(req.text, MAX_TEXT_CHARS)
        prompt = prompts.GRIEVANCE_EXTRACT.format(today=req.today.isoformat(), guard=prompts.GUARD, text=text)
        result = await self._client.generate(prompt, GrievanceAIOut, system=prompts.SYSTEM_BASE, temperature=0.0)
        if result.data is not None:
            facts = _to_facts(result.data, text, req.today)
            return Envelope(data=GrievanceDraft(facts=facts, summary=text), meta=_meta(request_id, result))
        facts = extract_grievance(text, req.today)
        return Envelope(data=GrievanceDraft(facts=facts, summary=text), meta=_meta(request_id, result))

    async def polish_letter(self, req: PolishRequest, request_id: str) -> Envelope[LetterText]:
        original = LetterText(subject=req.subject, body=redact_pii(req.body))
        prompt = prompts.POLISH.format(
            language=_language(req.lang), guard=prompts.GUARD, subject=original.subject, body=original.body
        )
        result = await self._client.generate(prompt, LetterText, system=prompts.SYSTEM_BASE)
        before = f"{original.subject}\n{original.body}"
        if result.data is not None and keeps_facts(before, f"{result.data.subject}\n{result.data.body}"):
            return Envelope(data=result.data, meta=_meta(request_id, result))
        reason = GUARD_REJECTED if result.ok else None
        return Envelope(data=original, meta=_meta(request_id, result, reason))

    async def welfare_summary(self, req: WelfareSummaryRequest, request_id: str) -> Envelope[WelfareSummary]:
        entry = self._store.entry(CONTENT_FILE, req.scheme_id)
        if entry is None:
            raise LookupError(req.scheme_id)
        local = localize(entry, req.lang, date.today())
        fallback = WelfareSummary(
            scheme_id=entry.id,
            summary=local.summary,
            steps=local.steps,
            official_url=entry.official_url,
            needs_verification=local.needs_verification,
        )
        key = (entry.id, req.lang, req.level)
        cached = self._welfare_cache.get(key)
        if cached is not None:
            meta = Meta(engine="gemini", degraded=False, model="cache", request_id=request_id)
            return Envelope(data=cached, meta=meta)
        facts = "\n".join(f"{i}. {s}" for i, s in enumerate(local.steps, 1))
        prompt = prompts.WELFARE.format(
            language=_language(req.lang),
            level=req.level,
            title=local.title,
            summary=local.summary,
            eligibility=local.eligibility,
            steps=facts,
        )
        result = await self._client.generate(prompt, WelfareAIOut, system=prompts.SYSTEM_BASE)
        source = f"{local.summary} {local.eligibility} {facts}"
        out = result.data
        if out is not None and _same_shape_no_new_facts(out, local.steps, source):
            summary = fallback.model_copy(update={"summary": out.summary, "steps": out.steps})
            self._welfare_cache.put(key, summary)
            return Envelope(data=summary, meta=_meta(request_id, result))
        reason = GUARD_REJECTED if result.ok else None
        return Envelope(data=fallback, meta=_meta(request_id, result, reason))

    async def day_gist(self, req: DayGistRequest, request_id: str) -> Envelope[DayGist]:
        text = sanitize_text(req.transcript, MAX_TEXT_CHARS)
        prompt = prompts.DAY_GIST.format(language=_language(req.lang), guard=prompts.GUARD, text=text)
        result = await self._client.generate(prompt, DayGist, system=prompts.SYSTEM_BASE, temperature=0.0)
        if result.data is not None:
            return Envelope(data=result.data, meta=_meta(request_id, result))
        return Envelope(data=extract_day_gist(text), meta=_meta(request_id, result))

    async def explain_contract(self, image: ImagePart, lang: Lang, request_id: str) -> Envelope[ContractExplanation]:
        prompt = prompts.CONTRACT.format(language=_language(lang))
        result = await self._client.generate(
            prompt, ContractExplanation, system=prompts.SYSTEM_BASE, temperature=0.1, image=image
        )
        if result.data is None:
            return Envelope(data=ContractExplanation(clauses=[], readable=False), meta=_meta(request_id, result))
        clauses = [
            Clause(title=redact_pii(c.title), explanation=redact_pii(c.explanation), caution=c.caution)
            for c in result.data.clauses
        ]
        data = ContractExplanation(clauses=clauses, readable=result.data.readable)
        return Envelope(data=data, meta=_meta(request_id, result))

    async def refine_triage(self, text: str, ctx: TriageContext) -> AIRefinement | None:
        """Optional AI refinement of Fix-It triage; None when unavailable or invalid."""
        if not text.strip():
            return None
        prompt = prompts.TRIAGE.format(
            categories=", ".join(c.value for c in Category),
            actions=", ".join(a.value for a in ActionId),
            route=ctx.route,
            errors=", ".join(ctx.recent_error_codes) or "none",
            language=_language(ctx.lang),
            guard=prompts.GUARD,
            text=sanitize_text(text, MAX_REPORT_CHARS),
        )
        result = await self._client.generate(prompt, AIRefinement, system=prompts.SYSTEM_BASE, temperature=0.0)
        return result.data


def _same_shape_no_new_facts(out: WelfareAIOut, steps: list[str], source: str) -> bool:
    """Simplified welfare text must keep the step count and add no numbers or links."""
    return len(out.steps) == len(steps) and not adds_facts(source, " ".join([out.summary, *out.steps]))


def _to_facts(out: GrievanceAIOut, source_text: str, today: date) -> GrievanceFacts:
    """Convert AI extraction to confirmed-fact types, dropping anything not supported by the text."""
    incident: date | None = None
    if out.incident_date:
        try:
            parsed = date.fromisoformat(out.incident_date)
            incident = parsed if parsed <= today else None
        except ValueError:
            incident = None
    amount: Decimal | None = None
    if out.amount_lost_inr is not None:
        try:
            candidate = Decimal(str(out.amount_lost_inr)).quantize(Decimal("0.01"))
        except InvalidOperation:
            candidate = None
        stated = fact_tokens(source_text)
        if candidate is not None and 0 <= candidate <= MAX_AMOUNT and format(candidate.normalize(), "f") in stated:
            amount = candidate
    platform = (out.platform or "").strip()[:40] or None
    return GrievanceFacts(
        date=incident, platform=platform, issue_type=out.issue_type, amount_lost=amount, remedy_sought=out.remedy_sought
    )
