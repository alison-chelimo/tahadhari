from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from ..database import get_db
from ..models import Feedback, Message, Profile
from ..schemas import FeedbackIn, FeedbackOut

router = APIRouter()

@router.post("/", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
def create_feedback(payload: FeedbackIn, db: Session = Depends(get_db)):
    if not db.query(Message).filter(Message.id == payload.message_id).first():
        raise HTTPException(status_code=404, detail=f"Message {payload.message_id} not found")
    if not db.query(Profile).filter(Profile.id == payload.profile_id).first():
        raise HTTPException(status_code=404, detail=f"Profile {payload.profile_id} not found")

    db_feedback = Feedback(
        message_id=payload.message_id,
        profile_id=payload.profile_id,
        feedback_type=payload.feedback_type.value,
        feedback_text=payload.feedback_text,
    )
    try:
        db.add(db_feedback)
        db.commit()
        db.refresh(db_feedback)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to persist feedback")
    return db_feedback

@router.get("/{feedback_id}", response_model=FeedbackOut)
def get_feedback(feedback_id: int, db: Session = Depends(get_db)):
    feedback = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail=f"Feedback {feedback_id} not found")
    return feedback
