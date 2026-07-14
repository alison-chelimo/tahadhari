import os
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from ..auth import require_service_or_admin
from ..database import commit_or_error, get_db
from ..models import RegistrationRequest
from ..schemas import (
    InboundMessageIn,
    RegistrationRequestOut,
    RegistrationRequestStateIn,
    RegistrationWebhookOut,
)

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
    # A row in "awaiting_location"/"location_resolved" is mid conversation for this
    # phone number -- route this inbound message by state instead of re-running keyword
    # detection on it. Once `awaiting_location` exists, the NEXT webhook call for that
    # number is unconditionally treated as the location answer, regardless of content --
    # there is no real gateway message-id to dedupe retries against, so this is a
    # deliberate design tradeoff (see the location-weather-conversation plan for the
    # reasoning). Deliberately keyed off `state`, not `resolved_at`: POST /profiles/ can
    # backfill profile_id/resolved_at on this row mid-conversation (see
    # app/routers/profiles.py::create_profile) without ending the conversation.
    pending = (
        db.query(RegistrationRequest)
        .filter(
            RegistrationRequest.phone_number == payload.phone_number,
            RegistrationRequest.state.isnot(None),
        )
        .order_by(RegistrationRequest.id.desc())
        .first()
    )
    if pending is not None:
        if pending.state == "awaiting_location":
            pending.raw_location_text = payload.text.strip()
            pending.state = "location_resolved"
            commit_or_error(db, pending, resource_name="registration request")
        # location_resolved/weather_delivered/failed: still being processed by ai_layer,
        # or terminal -- ack only, don't re-trigger.
        return RegistrationWebhookOut(
            matched=True, registration_request_id=pending.id, keyword=pending.matched_keyword,
            prompt=pending.state,
        )

    keyword = _detect_keyword(payload.text)
    if keyword is None:
        return RegistrationWebhookOut(matched=False)

    # Idempotency: a real gateway's webhook-delivery retries would otherwise create a
    # duplicate row per retry -- reuse an existing unresolved legacy (state=NULL) row for
    # this phone number instead of inserting a new one. New keyword matches always start
    # the location-conversation state machine, so this branch only ever matches rows
    # created before that machine existed.
    legacy_pending = (
        db.query(RegistrationRequest)
        .filter(
            RegistrationRequest.phone_number == payload.phone_number,
            RegistrationRequest.resolved_at.is_(None),
            RegistrationRequest.state.is_(None),
        )
        .first()
    )
    if legacy_pending is not None:
        return RegistrationWebhookOut(
            matched=True, registration_request_id=legacy_pending.id, keyword=legacy_pending.matched_keyword,
        )

    db_request = RegistrationRequest(
        phone_number=payload.phone_number,
        channel=payload.channel.value,
        raw_text=payload.text,
        matched_keyword=keyword,
        state="awaiting_location",
    )
    commit_or_error(db, db_request, resource_name="registration request")

    return RegistrationWebhookOut(
        matched=True, registration_request_id=db_request.id, keyword=keyword, prompt=db_request.state,
    )


@router.get("/requests", response_model=list[RegistrationRequestOut])
def list_registration_requests(
    resolved: bool | None = None,
    state: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(RegistrationRequest)
    if resolved is True:
        query = query.filter(RegistrationRequest.resolved_at.isnot(None))
    elif resolved is False:
        query = query.filter(RegistrationRequest.resolved_at.is_(None))
    if state is not None:
        query = query.filter(RegistrationRequest.state == state)
    return query.order_by(RegistrationRequest.id).offset(skip).limit(limit).all()


@router.patch("/requests/{request_id}/state", response_model=RegistrationRequestOut)
def update_registration_request_state(
    request_id: int, payload: RegistrationRequestStateIn, db: Session = Depends(get_db)
):
    """Used by ai_layer's location-weather poller to advance a request past
    `location_resolved` once it has produced a Message (`weather_delivered`) or given up
    (`failed`) -- see ai_layer/services/location_weather.py."""
    db_request = db.query(RegistrationRequest).filter(RegistrationRequest.id == request_id).first()
    if not db_request:
        raise HTTPException(status_code=404, detail=f"Registration request {request_id} not found")

    db_request.state = payload.state
    if payload.state == "weather_delivered":
        db_request.resolved_at = func.now()
    commit_or_error(db, db_request, resource_name="registration request")
    return db_request
