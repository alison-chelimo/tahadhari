from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..auth import require_service_or_admin
from ..database import commit_or_error, get_db
from ..models import Message, Profile, Alert, ActionTemplate, FloodPrediction
from ..schemas import MessageIn, MessageOut

router = APIRouter(dependencies=[Depends(require_service_or_admin)])

@router.post("/", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def create_message(payload: MessageIn, db: Session = Depends(get_db)):
    if not db.query(Profile).filter(Profile.id == payload.profile_id).first():
        raise HTTPException(status_code=404, detail=f"Profile {payload.profile_id} not found")
    if not db.query(Alert).filter(Alert.id == payload.alert_id).first():
        raise HTTPException(status_code=404, detail=f"Alert {payload.alert_id} not found")
    if payload.template_id is not None and not db.query(ActionTemplate).filter(ActionTemplate.id == payload.template_id).first():
        raise HTTPException(status_code=404, detail=f"ActionTemplate {payload.template_id} not found")
    if payload.flood_prediction_id is not None and not db.query(FloodPrediction).filter(FloodPrediction.id == payload.flood_prediction_id).first():
        raise HTTPException(status_code=404, detail=f"FloodPrediction {payload.flood_prediction_id} not found")

    data = payload.model_dump()
    data["channel"] = payload.channel.value
    db_message = Message(**data)
    return commit_or_error(db, db_message, resource_name="message")

@router.get("/{message_id}", response_model=MessageOut)
def get_message(message_id: int, db: Session = Depends(get_db)):
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail=f"Message {message_id} not found")
    return message
