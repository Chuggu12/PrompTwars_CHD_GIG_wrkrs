"""Server mirror of the browser action registry (app/static/js/selfheal/actions.js).

Every action has a risk level and a parameter model with tight bounds. Anything that
is not in ACTION_SPECS, or has out-of-range params, is rejected.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.constants import Lang

from .schemas import ActionId, ParamValue, ProposedAction, Risk

ViewName = Literal["home", "earnings", "rights", "documents", "more", "settings", "grievance", "checkin", "health"]


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoParams(_Params):
    pass


class FontScaleParams(_Params):
    scale: float = Field(ge=1.0, le=1.6)


class ToggleParams(_Params):
    enabled: bool


class LanguageParams(_Params):
    lang: Lang


class ReadingLevelParams(_Params):
    level: Literal["simple", "standard"]


class AlertCapParams(_Params):
    max_per_day: int = Field(ge=0, le=3)


class MuteAlertParams(_Params):
    alert_type: str = Field(pattern=r"^[a-z_]{1,30}$")


class ManualEntryParams(_Params):
    mode: Literal["voice", "scan"]


class ViewParams(_Params):
    view: ViewName


class RecalcParams(_Params):
    date: dt.date | None = None


@dataclass(frozen=True)
class ActionSpec:
    risk: Risk
    params: type[_Params]


ACTION_SPECS: dict[ActionId, ActionSpec] = {
    ActionId.SET_FONT_SCALE: ActionSpec("safe", FontScaleParams),
    ActionId.SET_HIGH_CONTRAST: ActionSpec("safe", ToggleParams),
    ActionId.SET_LANGUAGE: ActionSpec("safe", LanguageParams),
    ActionId.SET_READING_LEVEL: ActionSpec("safe", ReadingLevelParams),
    ActionId.SET_READ_ALOUD_DEFAULT: ActionSpec("safe", ToggleParams),
    ActionId.REDUCE_ALERT_FREQUENCY: ActionSpec("safe", AlertCapParams),
    ActionId.MUTE_ALERT_TYPE: ActionSpec("safe", MuteAlertParams),
    ActionId.ENABLE_QUIET_MODE: ActionSpec("safe", ToggleParams),
    ActionId.ENABLE_LITE_MODE: ActionSpec("safe", ToggleParams),
    ActionId.SWITCH_TO_MANUAL_ENTRY: ActionSpec("safe", ManualEntryParams),
    ActionId.CLEAR_UI_CACHE_AND_RELOAD: ActionSpec("confirm", NoParams),
    ActionId.RESET_VIEW_STATE: ActionSpec("safe", ViewParams),
    ActionId.REFRESH_DATA_FILES: ActionSpec("safe", NoParams),
    ActionId.RECHECK_AI_MODELS: ActionSpec("safe", NoParams),
    ActionId.RECALC_AND_EXPLAIN: ActionSpec("safe", RecalcParams),
    ActionId.REPAIR_STORAGE: ActionSpec("confirm", NoParams),
    ActionId.OPEN_HUMAN_HELP: ActionSpec("safe", NoParams),
    ActionId.SUBMIT_REPORT: ActionSpec("confirm", NoParams),
}


class UnknownActionError(ValueError):
    """Raised for an action id that is not whitelisted."""


def validate_action(action_id: str, params: dict[str, ParamValue]) -> ProposedAction:
    """Return a validated action or raise UnknownActionError / ValueError."""
    try:
        key = ActionId(action_id)
    except ValueError as exc:
        raise UnknownActionError(action_id) from exc
    spec = ACTION_SPECS[key]
    try:
        model = spec.params.model_validate(params)
    except ValidationError as exc:
        raise ValueError(f"invalid params for {action_id}") from exc
    return ProposedAction(action_id=key, params=model.model_dump(mode="json"), risk=spec.risk)
