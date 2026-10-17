"""Deterministic-first triage of a worker's problem report.

1. Keyword/phrase matching from data/triage-keywords.json (all 4 languages) plus
   context signals gives a Diagnosis that always works offline.
2. If the AI is available, its refinement may change the category and pick action ids
   from the same closed enums. Parameters are ALWAYS computed here, never by the AI.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from typing import Final

from app.domain.constants import Lang

from .actions import UnknownActionError, validate_action
from .schemas import (
    ActionId,
    AIRefinement,
    Category,
    Clarify,
    Diagnosis,
    ParamValue,
    ProposedAction,
    TriageBook,
    TriageContext,
)

CLARIFY_THRESHOLD: Final = 0.6
BASE_CONFIDENCE: Final = 0.4
CONFIDENCE_PER_POINT: Final = 0.15
MAX_CONFIDENCE: Final = 0.95
AMBIGUOUS_CONFIDENCE: Final = 0.5
CONTEXT_CONFIDENCE: Final = 0.6
FONT_STEP: Final = 0.2
FONT_MAX: Final = 1.6
REDUCED_ALERT_CAP: Final = 1

_SCRIPTS: Final[tuple[tuple[Lang, re.Pattern[str]], ...]] = (
    ("hi", re.compile(r"[\u0900-\u097f]")),
    ("ta", re.compile(r"[\u0b80-\u0bff]")),
    ("pa", re.compile(r"[\u0a00-\u0a7f]")),
)


def normalize(text: str) -> str:
    """Lower-case, NFKC, apostrophes removed, whitespace collapsed (for matching)."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"['\u2019`]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_script(text: str) -> Lang:
    """Language of the report by script (Latin -> English)."""
    for lang, pattern in _SCRIPTS:
        if pattern.search(text):
            return lang
    return "en"


def score_categories(text: str, book: TriageBook) -> dict[Category, int]:
    """Phrase score per category: each matched keyword adds its word count."""
    norm = normalize(text)
    scores: dict[Category, int] = {}
    for category, spec in book.categories.items():
        score = sum(
            len(keyword.split())
            for words in spec.keywords.values()
            for keyword in (normalize(w) for w in words)
            if keyword and keyword in norm
        )
        if score:
            scores[category] = score
    return scores


def _confidence(scores: dict[Category, int]) -> tuple[Category, float]:
    if not scores:
        return Category.OTHER, 0.2
    ranked = sorted(scores.items(), key=lambda item: -item[1])
    top, top_score = ranked[0]
    confidence = min(BASE_CONFIDENCE + CONFIDENCE_PER_POINT * top_score, MAX_CONFIDENCE)
    if len(ranked) > 1 and ranked[1][1] == top_score:
        confidence = min(confidence, AMBIGUOUS_CONFIDENCE)
    return top, confidence


def _mentioned_alert_type(text: str, book: TriageBook) -> str | None:
    norm = normalize(text)
    for alert_type, words in book.alert_type_words.items():
        if any(normalize(w) in norm for w in words):
            return alert_type
    return None


# Actions whose params never depend on context.
_FIXED_PARAMS: Final[dict[ActionId, dict[str, ParamValue]]] = {
    ActionId.SET_HIGH_CONTRAST: {"enabled": True},
    ActionId.SET_READ_ALOUD_DEFAULT: {"enabled": True},
    ActionId.ENABLE_QUIET_MODE: {"enabled": True},
    ActionId.ENABLE_LITE_MODE: {"enabled": True},
    ActionId.SET_READING_LEVEL: {"level": "simple"},
    ActionId.SWITCH_TO_MANUAL_ENTRY: {"mode": "voice"},
}


def _language_params(ctx: TriageContext, text: str) -> dict[str, ParamValue] | None:
    text_lang = detect_script(text) if text else ctx.lang
    return {"lang": text_lang} if text_lang != ctx.lang else None


def _alert_type_params(text: str, book: TriageBook) -> dict[str, ParamValue] | None:
    alert_type = _mentioned_alert_type(text, book)
    return {"alert_type": alert_type} if alert_type else None


def params_for(action: ActionId, ctx: TriageContext, text: str, book: TriageBook) -> dict[str, ParamValue] | None:
    """Deterministic, bounded params for an action. None means 'skip this action'."""
    if action in _FIXED_PARAMS:
        return dict(_FIXED_PARAMS[action])
    contextual: dict[ActionId, Callable[[], dict[str, ParamValue] | None]] = {
        ActionId.SET_FONT_SCALE: lambda: {"scale": round(min(ctx.font_scale + FONT_STEP, FONT_MAX), 1)},
        ActionId.SET_LANGUAGE: lambda: _language_params(ctx, text),
        ActionId.REDUCE_ALERT_FREQUENCY: lambda: {"max_per_day": min(REDUCED_ALERT_CAP, ctx.alert_cap)},
        ActionId.MUTE_ALERT_TYPE: lambda: _alert_type_params(text, book),
        ActionId.RESET_VIEW_STATE: lambda: {"view": ctx.last_failed_module or ctx.route},
        ActionId.RECALC_AND_EXPLAIN: lambda: {"date": ctx.today.isoformat() if ctx.today else None},
    }
    builder = contextual.get(action)
    return builder() if builder else {}


def build_actions(ids: list[ActionId], ctx: TriageContext, text: str, book: TriageBook) -> list[ProposedAction]:
    """Validate every proposed action against the whitelist; drop anything invalid."""
    actions: list[ProposedAction] = []
    for action_id in dict.fromkeys(ids):
        params = params_for(action_id, ctx, text, book)
        if params is None:
            continue
        try:
            actions.append(validate_action(action_id.value, params))
        except (UnknownActionError, ValueError):
            continue
    return actions


def _context_signals(
    category: Category, confidence: float, ctx: TriageContext
) -> tuple[Category, float, list[ActionId]]:
    """Use recent client errors and model status to sharpen a weak diagnosis."""
    extra: list[ActionId] = []
    if ctx.recent_error_codes and confidence < CLARIFY_THRESHOLD:
        category, confidence = Category.FEATURE_BROKEN, CONTEXT_CONFIDENCE
    if category is Category.FEATURE_BROKEN:
        if ctx.last_failed_module:
            extra.append(ActionId.RESET_VIEW_STATE)
        if ctx.ai_status == "degraded":
            extra.append(ActionId.RECHECK_AI_MODELS)
    return category, confidence, extra


def _diagnosis(
    category: Category,
    confidence: float,
    ids: list[ActionId],
    *,
    ctx: TriageContext,
    text: str,
    book: TriageBook,
    message: str | None = None,
) -> Diagnosis:
    spec = book.categories[category]
    actions = build_actions(ids, ctx, text, book)
    unsure = confidence < CLARIFY_THRESHOLD or category is Category.OTHER
    default_message = spec.message.get(ctx.lang) or spec.message["en"]
    clarify = None
    if unsure:
        other = book.categories[Category.OTHER]
        clarify = Clarify(question=other.message.get(ctx.lang) or other.message["en"], chips=book.clarify_chips)
    return Diagnosis(
        category=category,
        severity=spec.severity,
        confidence=round(confidence, 2),
        user_message=message or default_message,
        actions=actions,
        needs_confirmation=any(a.risk == "confirm" for a in actions),
        escalate=spec.severity == "high" or category in (Category.FEATURE_REQUEST, Category.OTHER),
        clarify=clarify,
    )


def triage(text: str, ctx: TriageContext, book: TriageBook, chosen: Category | None = None) -> Diagnosis:
    """Deterministic diagnosis. A category chosen from a clarify chip is trusted fully."""
    if chosen is not None:
        category, confidence = chosen, 1.0
    else:
        category, confidence = _confidence(score_categories(text, book))
    category, confidence, extra = _context_signals(category, confidence, ctx)
    ids = list(book.categories[category].actions) + extra
    return _diagnosis(category, confidence, ids, ctx=ctx, text=text, book=book)


def merge_refinement(base: Diagnosis, ai: AIRefinement, ctx: TriageContext, text: str, book: TriageBook) -> Diagnosis:
    """Prefer the AI category when it is more confident; actions stay whitelisted."""
    if ai.confidence <= base.confidence and base.category is not Category.OTHER:
        return base
    ids = ai.action_ids or list(book.categories[ai.category].actions)
    message = ai.user_message.strip() or None
    return _diagnosis(ai.category, ai.confidence, ids, ctx=ctx, text=text, book=book, message=message)
