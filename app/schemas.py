from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

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


class MessageIn(BaseModel):
    profile_id: int
    alert_id: int
    template_id: Optional[int] = None
    flood_prediction_id: Optional[int] = None
    final_text: str
    channel: str  # "whatsapp" or "sms"


class MessageOut(BaseModel):
    id: int
    profile_id: int
    alert_id: int
    template_id: Optional[int]
    flood_prediction_id: Optional[int]
    final_text: str
    channel: str
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