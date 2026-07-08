from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from ..auth import require_service_or_admin
from ..database import get_db
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

    db_message = Message(**payload.model_dump())
    try:
        db.add(db_message)
        db.commit()
        db.refresh(db_message)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to persist message")
    return db_message

@router.get("/{message_id}", response_model=MessageOut)
def get_message(message_id: int, db: Session = Depends(get_db)):
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail=f"Message {message_id} not found")
    return message
