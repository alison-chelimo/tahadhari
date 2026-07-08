import re
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

ROUTE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


# ---- mirrors of Alison's DB-backed resources ----

class AlertIn(BaseModel):
    """Mirrors app.schemas.AlertIn -- used when ai_layer ingests a new alert via the API."""
    source: str
    geography_type: Literal["ward", "corridor"]
    geography_ref: str
    rainfall_mm: float
    raw_payload: Optional[dict[str, Any]] = None


class Alert(BaseModel):
    """Mirrors app.schemas.AlertOut."""
    id: int
    hazard_type: str
    severity: str
    geography_type: Literal["ward", "corridor"]
    geography_ref: str
    rainfall_mm: float
    created_at: datetime


class Profile(BaseModel):
    """Mirrors app.models.Profile.

    route_id contract (formal, documented here since ai_layer has no DB access):
    when set, `route_id` stores a `road_segments.segment_name` value directly
    (e.g. "Adams_Arcade") -- matching the `segment` string returned by
    POST /alerts/predict/{alert_id}. This is NOT a real foreign key from
    ai_layer's point of view: the validator below can only check the value is
    structurally well-formed (non-empty, `^[A-Za-z0-9_]+$` -- no spaces, matching
    the naming convention actually used by the seeded road_segments rows). It
    cannot and does not confirm the value matches a real, currently-seeded
    segment; that can only be discovered by calling the live API
    (see services/template_selector.py's corridor-track lookup).
    """
    id: int
    phone_number: str
    channel: Literal["whatsapp", "sms"]
    language: str = "en"
    user_type: Literal["rural", "urban"]
    occupation: Optional[str] = None
    ward: Optional[str] = None
    route_id: Optional[str] = None
    key_asset: Optional[str] = None
    registration_source: Optional[str] = None
    registered_by: Optional[str] = None

    @field_validator("route_id")
    @classmethod
    def validate_route_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not v or not ROUTE_ID_PATTERN.fullmatch(v):
            raise ValueError(
                f"route_id {v!r} must be a non-empty string matching ^[A-Za-z0-9_]+$ "
                "(the road_segments.segment_name naming convention) -- see class docstring"
            )
        return v


class ActionTemplate(BaseModel):
    id: int
    hazard_type: str
    occupation: str
    severity: str
    language: str = "en"
    template_text: str


class PredictionRecord(BaseModel):
    """One flagged segment as returned by POST /alerts/predict/{alert_id}."""
    segment_name: str
    risk_level: str
    flood_prediction_id: Optional[int] = None
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None


# ---- select_content()'s tagged-union result ----

class TemplateMatch(BaseModel):
    kind: Literal["template_match"] = "template_match"
    alert: Alert
    profile: Profile
    template: ActionTemplate


class PredictionMatch(BaseModel):
    kind: Literal["prediction_match"] = "prediction_match"
    alert: Alert
    profile: Profile
    segment_name: str
    risk_level: str
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    flood_prediction_id: Optional[int] = None


class NoMatch(BaseModel):
    kind: Literal["no_match"] = "no_match"
    alert: Alert
    profile: Profile
    reason: str


SelectionResult = Union[TemplateMatch, PredictionMatch, NoMatch]


# ---- messages ----

class MessageIn(BaseModel):
    profile_id: int
    alert_id: int
    template_id: Optional[int] = None
    flood_prediction_id: Optional[int] = None
    final_text: str
    channel: Literal["whatsapp", "sms"]


class Message(BaseModel):
    """Mirrors app.schemas.MessageOut."""
    id: int
    profile_id: int
    alert_id: int
    template_id: Optional[int] = None
    flood_prediction_id: Optional[int] = None
    final_text: str
    channel: str
    delivery_status: str
    sent_at: datetime


# ---- feedback ----

class FeedbackCategory(str, Enum):
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"
    INCORRECT_LOCATION = "incorrect_location"
    INCORRECT_TIMING = "incorrect_timing"
    UNCLEAR = "unclear"
    OTHER = "other"


class FeedbackClassification(BaseModel):
    """Strict structured-output schema Claude must fill via client.messages.parse()."""
    category: FeedbackCategory
    confidence: float = Field(ge=0.0, le=1.0)


class FeedbackIn(BaseModel):
    message_id: int
    profile_id: int
    feedback_type: FeedbackCategory
    feedback_text: Optional[str] = None


class Feedback(BaseModel):
    """Both classify_feedback()'s return type AND the typed mirror of
    app.schemas.FeedbackOut once persisted. `confidence`/`classification_failed`
    are ai_layer-domain-only -- there is no DB column for them, so they are
    never sent in FeedbackIn; they exist for logging/introspection only."""
    id: Optional[int] = None
    message_id: int
    profile_id: int
    feedback_type: FeedbackCategory
    feedback_text: Optional[str] = None
    confidence: Optional[float] = None
    classification_failed: bool = False
    created_at: Optional[datetime] = None
