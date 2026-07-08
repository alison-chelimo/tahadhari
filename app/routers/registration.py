import os
import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..auth import require_service_or_admin
from ..database import commit_or_error, get_db
from ..models import RegistrationRequest
from ..schemas import InboundMessageIn, RegistrationRequestOut, RegistrationWebhookOut

router = APIRouter(dependencies=[Depends(require_service_or_admin)])

# Env-overridable, comma-separated, case-insensitive. Ships with a single English default --
# no other-language keyword translations are guessed here; add real ones via the env var.
REGISTRATION_KEYWORDS = {
    kw.strip().casefold()
    for kw in os.getenv("REGISTRATION_KEYWORDS", "REGISTER").split(",")
    if kw.strip()
}

_LEADING_WORD_RE = re.compile(r"[A-Za-z]+")


def _detect_keyword(text: str) -> str | None:
    match = _LEADING_WORD_RE.match(text.strip())
    if not match:
        return None
    candidate = match.group(0).casefold()
    return candidate if candidate in REGISTRATION_KEYWORDS else None


@router.post("/webhook", response_model=RegistrationWebhookOut)
def registration_webhook(payload: InboundMessageIn, db: Session = Depends(get_db)):
    keyword = _detect_keyword(payload.text)
    if keyword is None:
        return RegistrationWebhookOut(matched=False)

    # Idempotency: a real gateway's webhook-delivery retries would otherwise create a
    # duplicate row per retry -- reuse the existing pending request for this phone
    # number instead of inserting a new one.
    pending = (
        db.query(RegistrationRequest)
        .filter(
            RegistrationRequest.phone_number == payload.phone_number,
            RegistrationRequest.resolved_at.is_(None),
        )
        .first()
    )
    if pending is not None:
        return RegistrationWebhookOut(
            matched=True, registration_request_id=pending.id, keyword=pending.matched_keyword,
        )

    db_request = RegistrationRequest(
        phone_number=payload.phone_number,
        channel=payload.channel.value,
        raw_text=payload.text,
        matched_keyword=keyword,
    )
    commit_or_error(db, db_request, resource_name="registration request")

    return RegistrationWebhookOut(matched=True, registration_request_id=db_request.id, keyword=keyword)


@router.get("/requests", response_model=list[RegistrationRequestOut])
def list_registration_requests(
    resolved: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(RegistrationRequest)
    if resolved is True:
        query = query.filter(RegistrationRequest.resolved_at.isnot(None))
    elif resolved is False:
        query = query.filter(RegistrationRequest.resolved_at.is_(None))
    return query.order_by(RegistrationRequest.id).offset(skip).limit(limit).all()
