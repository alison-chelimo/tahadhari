from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from .database import Base

class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, index=True)
    hazard_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    geography_type = Column(String, nullable=False)  # "ward" or "corridor"
    geography_ref = Column(String, nullable=False)
    rainfall_mm = Column(Float)
    source = Column(String)
    raw_payload = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Profile(Base):
    __tablename__ = "profiles"
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, unique=True, nullable=False)
    channel = Column(String, nullable=False)  # "whatsapp" or "sms"
    language = Column(String, default="en")
    user_type = Column(String, nullable=False)  # "rural" or "urban"
    occupation = Column(String, nullable=True)
    ward = Column(String, nullable=True)
    route_id = Column(String, nullable=True)
    key_asset = Column(String, nullable=True)
    registration_source = Column(String, nullable=False)  # "whatsapp_keyword" / "sms_keyword" / "partner_assisted"
    registered_by = Column(String, nullable=True)  # CHW/chief identifier; set only for partner_assisted

class RegistrationRequest(Base):
    """A detected registration-keyword intent, logged for a partner/admin to follow up on.
    Not linked to Profile -- completing registration is a separate later POST /profiles/."""
    __tablename__ = "registration_requests"
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, nullable=False, index=True)
    channel = Column(String, nullable=False)  # "whatsapp" or "sms"
    raw_text = Column(String, nullable=False)
    matched_keyword = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ActionTemplate(Base):
    __tablename__ = "action_templates"
    id = Column(Integer, primary_key=True, index=True)
    hazard_type = Column(String, nullable=False)
    occupation = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    language = Column(String, default="en")
    template_text = Column(String, nullable=False)

class RoadSegment(Base):
    __tablename__ = "road_segments"
    id = Column(Integer, primary_key=True, index=True)
    corridor_name = Column(String, nullable=False)
    segment_name = Column(String, nullable=False)
    start_lat = Column(Float)
    start_lon = Column(Float)
    end_lat = Column(Float)
    end_lon = Column(Float)
    drainage_capacity_mm = Column(Float, nullable=False)

class FloodPrediction(Base):
    __tablename__ = "flood_predictions"
    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"))
    segment_id = Column(Integer, ForeignKey("road_segments.id"))
    risk_level = Column(String, nullable=False)
    window_start = Column(DateTime)
    window_end = Column(DateTime)

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    template_id = Column(Integer, ForeignKey("action_templates.id"), nullable=True)
    flood_prediction_id = Column(Integer, ForeignKey("flood_predictions.id"), nullable=True)
    final_text = Column(String, nullable=False)
    channel = Column(String, nullable=False)  # "whatsapp" or "sms"
    delivery_status = Column(String, default="pending")  # pending/sent/failed
    sent_at = Column(DateTime(timezone=True), server_default=func.now())

class Feedback(Base):
    __tablename__ = "feedback"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False)
    feedback_type = Column(String, nullable=False)  # e.g. "inaccurate", "unhelpful", "confirmed", "correction"
    feedback_text = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AdminUser(Base):
    __tablename__ = "admin_users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())