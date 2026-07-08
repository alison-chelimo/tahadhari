from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..auth import require_service_or_admin
from ..database import commit_or_error, get_db
from ..models import Feedback, Message, Profile
from ..schemas import FeedbackIn, FeedbackOut

router = APIRouter(dependencies=[Depends(require_service_or_admin)])

@router.post("/", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
def create_feedback(payload: FeedbackIn, db: Session = Depends(get_db)):
    message = db.query(Message).filter(Message.id == payload.message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail=f"Message {payload.message_id} not found")
    if not db.query(Profile).filter(Profile.id == payload.profile_id).first():
        raise HTTPException(status_code=404, detail=f"Profile {payload.profile_id} not found")
    if message.profile_id != payload.profile_id:
        raise HTTPException(status_code=400, detail="profile_id does not match message's profile_id")

    db_feedback = Feedback(
        message_id=payload.message_id,
        profile_id=payload.profile_id,
        feedback_type=payload.feedback_type.value,
        feedback_text=payload.feedback_text,
    )
    return commit_or_error(db, db_feedback, resource_name="feedback")

@router.get("/{feedback_id}", response_model=FeedbackOut)
def get_feedback(feedback_id: int, db: Session = Depends(get_db)):
    feedback = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail=f"Feedback {feedback_id} not found")
    return feedback
