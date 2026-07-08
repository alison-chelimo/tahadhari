from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..auth import get_current_admin, require_service_or_admin
from ..database import get_db
from ..models import ActionTemplate
from pydantic import BaseModel

router = APIRouter()

class TemplateIn(BaseModel):
    hazard_type: str
    occupation: str
    severity: str
    language: str = "en"
    template_text: str

@router.post("/", dependencies=[Depends(get_current_admin)])
def create_template(t: TemplateIn, db: Session = Depends(get_db)):
    db_t = ActionTemplate(**t.dict())
    db.add(db_t)
    db.commit()
    db.refresh(db_t)
    return db_t

@router.get("/match", dependencies=[Depends(require_service_or_admin)])
def match_template(hazard_type: str, occupation: str, severity: str, language: str = "en", db: Session = Depends(get_db)):
    return db.query(ActionTemplate).filter_by(
        hazard_type=hazard_type, occupation=occupation,
        severity=severity, language=language
    ).all()