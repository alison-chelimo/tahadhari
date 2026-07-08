import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from ..auth import require_service_or_admin
from ..database import get_db
from ..models import RegistrationRequest
from ..schemas import InboundMessageIn, RegistrationWebhookOut

router = APIRouter(dependencies=[Depends(require_service_or_admin)])

# Env-overridable, comma-separated, case-insensitive. Ships with a single English default --
# no other-language keyword translations are guessed here; add real ones via the env var.
REGISTRATION_KEYWORDS = {
    kw.strip().casefold()
    for kw in os.getenv("REGISTRATION_KEYWORDS", "REGISTER").split(",")
    if kw.strip()
}


def _detect_keyword(text: str) -> str | None:
    normalized = text.strip().casefold()
    for kw in REGISTRATION_KEYWORDS:
        if normalized == kw or normalized.startswith(f"{kw} "):
            return kw
    return None


@router.post("/webhook", response_model=RegistrationWebhookOut)
def registration_webhook(payload: InboundMessageIn, db: Session = Depends(get_db)):
    keyword = _detect_keyword(payload.text)
    if keyword is None:
        return RegistrationWebhookOut(matched=False)

    db_request = RegistrationRequest(
        phone_number=payload.phone_number,
        channel=payload.channel.value,
        raw_text=payload.text,
        matched_keyword=keyword,
    )
    try:
        db.add(db_request)
        db.commit()
        db.refresh(db_request)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to persist registration request")

    return RegistrationWebhookOut(matched=True, registration_request_id=db_request.id, keyword=keyword)
