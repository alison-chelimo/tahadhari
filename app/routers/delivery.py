import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_service_or_admin
from ..database import get_db
from ..models import Message, Profile
from ..schemas import DeliveryAttemptIn, DeliveryAttemptOut, Channel
from ..services.delivery import DeliveryError, deliver_message

router = APIRouter(dependencies=[Depends(require_service_or_admin)])
logger = logging.getLogger(__name__)


@router.post("/messages/{message_id}/send", response_model=DeliveryAttemptOut)
def send_message(message_id: int, payload: DeliveryAttemptIn, db: Session = Depends(get_db)):
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail=f"Message {message_id} not found")

    profile = db.query(Profile).filter(Profile.id == message.profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {message.profile_id} not found")

    requested_channel = payload.force_channel.value if payload.force_channel else message.channel
    if requested_channel not in (Channel.TELEGRAM.value, Channel.WHATSAPP.value, Channel.SMS.value):
        raise HTTPException(status_code=400, detail=f"Unsupported channel {requested_channel!r}")

    try:
        result = deliver_message(
            requested_channel,
            profile.phone_number,
            message.final_text,
            media_url=payload.media_url,
        )
        message.delivery_status = "sent"
        db.commit()
        return DeliveryAttemptOut(
            message_id=message.id,
            channel=requested_channel,
            delivery_status=message.delivery_status,
            provider=result.provider,
            provider_message_id=result.provider_message_id,
            detail=result.detail,
        )
    except DeliveryError as exc:
        logger.warning(
            "Delivery failed for message_id=%s profile_id=%s channel=%s: %s",
            message.id,
            profile.id,
            requested_channel,
            exc,
        )
        message.delivery_status = "failed"
        db.commit()
        return DeliveryAttemptOut(
            message_id=message.id,
            channel=requested_channel,
            delivery_status=message.delivery_status,
            provider="none",
            provider_message_id=None,
            detail=str(exc),
        )
