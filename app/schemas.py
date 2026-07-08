import re
from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

# Duplicated intentionally from ai_layer.schemas.ROUTE_ID_PATTERN -- app and ai_layer are
# independently deployable with no cross-import, so keep the two patterns in sync by hand.
ROUTE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")

class AlertIn(BaseModel):
    source: str
    geography_type: str  # "ward" or "corridor"
    geography_ref: str
    rainfall_mm: float
    raw_payload: Optional[Dict[str, Any]] = None

class AlertOut(BaseModel):
    id: int
    hazard_type: str
    severity: str
    geography_type: str
    geography_ref: str
    rainfall_mm: float
    created_at: datetime

    class Config:
        from_attributes = True


class Channel(str, Enum):
    WHATSAPP = "whatsapp"
    SMS = "sms"


class MessageIn(BaseModel):
    profile_id: int
    alert_id: int
    template_id: Optional[int] = None
    flood_prediction_id: Optional[int] = None
    final_text: str
    channel: Channel


class MessageOut(BaseModel):
    id: int
    profile_id: int
    alert_id: int
    template_id: Optional[int]
    flood_prediction_id: Optional[int]
    final_text: str
    channel: Channel
    delivery_status: str
    sent_at: datetime

    class Config:
        from_attributes = True


class FeedbackType(str, Enum):
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"
    INCORRECT_LOCATION = "incorrect_location"
    INCORRECT_TIMING = "incorrect_timing"
    UNCLEAR = "unclear"
    OTHER = "other"


class FeedbackIn(BaseModel):
    message_id: int
    profile_id: int
    feedback_type: FeedbackType
    feedback_text: Optional[str] = None


class FeedbackOut(BaseModel):
    id: int
    message_id: int
    profile_id: int
    feedback_type: str
    feedback_text: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserType(str, Enum):
    RURAL = "rural"
    URBAN = "urban"


class RegistrationSource(str, Enum):
    WHATSAPP_KEYWORD = "whatsapp_keyword"
    SMS_KEYWORD = "sms_keyword"
    PARTNER_ASSISTED = "partner_assisted"


class _ProfileFields(BaseModel):
    phone_number: str
    channel: Channel
    language: str = "en"
    user_type: UserType
    occupation: Optional[str] = None
    ward: Optional[str] = None
    route_id: Optional[str] = None
    key_asset: Optional[str] = None
    registration_source: RegistrationSource
    registered_by: Optional[str] = None


class ProfileIn(_ProfileFields):
    @field_validator("route_id")
    @classmethod
    def validate_route_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not v or not ROUTE_ID_PATTERN.fullmatch(v):
            raise ValueError(f"route_id {v!r} must be a non-empty string matching {ROUTE_ID_PATTERN.pattern}")
        return v

    @model_validator(mode="after")
    def validate_conditional_fields(self) -> "ProfileIn":
        errors = []
        if self.user_type == UserType.RURAL and (not self.ward or not self.occupation or not self.key_asset):
            errors.append("rural registrations require ward, occupation, and key_asset")
        if self.user_type == UserType.URBAN and not self.route_id:
            errors.append("urban registrations require route_id")
        if self.registration_source == RegistrationSource.PARTNER_ASSISTED and not self.registered_by:
            errors.append("partner-assisted registrations require registered_by")
        if errors:
            raise ValueError("; ".join(errors))
        return self


class ProfileOut(_ProfileFields):
    id: int

    class Config:
        from_attributes = True


class InboundMessageIn(BaseModel):
    """Provider-agnostic inbound message shape. Mapping a real WhatsApp/SMS gateway's
    actual webhook payload to this shape is future integration work -- no gateway is
    wired up yet."""
    phone_number: str
    channel: Channel
    text: str


class RegistrationWebhookOut(BaseModel):
    matched: bool
    registration_request_id: Optional[int] = None
    keyword: Optional[str] = None


class RegistrationRequestOut(BaseModel):
    id: int
    phone_number: str
    channel: str
    raw_text: str
    matched_keyword: Optional[str]
    profile_id: Optional[int]
    resolved_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True