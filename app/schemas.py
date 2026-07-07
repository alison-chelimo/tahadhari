from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

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