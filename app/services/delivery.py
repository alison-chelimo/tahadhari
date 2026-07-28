import os
import logging
from dataclasses import dataclass

import httpx


logger = logging.getLogger(__name__)


class DeliveryError(Exception):
    pass


@dataclass
class DeliveryResult:
    provider: str
    provider_message_id: str | None
    detail: str


def _send_sms_via_twilio(phone_number: str, body_text: str, media_url: str | None = None) -> DeliveryResult:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_SMS_FROM")
    if not account_sid or not auth_token or not from_number:
        raise DeliveryError("missing TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, or TWILIO_SMS_FROM")

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    payload = {
        "To": phone_number,
        "From": from_number,
        "Body": body_text,
    }
    if media_url:
        payload["MediaUrl"] = media_url

    response = httpx.post(url, data=payload, auth=(account_sid, auth_token), timeout=15.0)
    if response.status_code >= 400:
        raise DeliveryError(f"Twilio SMS API error: {response.status_code} {response.text}")

    data = response.json()
    return DeliveryResult(provider="twilio_sms", provider_message_id=data.get("sid"), detail="sent via Twilio SMS")


def _send_via_telegram(chat_id: str, body_text: str, media_url: str | None = None) -> DeliveryResult:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise DeliveryError("missing TELEGRAM_BOT_TOKEN")

    base_url = f"https://api.telegram.org/bot{bot_token}"
    if media_url:
        endpoint = f"{base_url}/sendPhoto"
        payload = {
            "chat_id": chat_id,
            "photo": media_url,
            "caption": body_text[:1024],
        }
    else:
        endpoint = f"{base_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": body_text,
        }

    response = httpx.post(endpoint, json=payload, timeout=15.0)
    if response.status_code >= 400:
        raise DeliveryError(f"Telegram API error: {response.status_code} {response.text}")

    data = response.json()
    if not data.get("ok"):
        raise DeliveryError(f"Telegram API rejected message: {data}")

    message_id = None
    result = data.get("result")
    if isinstance(result, dict):
        message_id = result.get("message_id")

    return DeliveryResult(provider="telegram", provider_message_id=str(message_id) if message_id else None, detail="sent via Telegram Bot API")


def _mock_delivery(channel: str) -> DeliveryResult:
    provider = "mock_telegram" if channel == "telegram" else "mock_sms"
    return DeliveryResult(provider=provider, provider_message_id="mock-msg-001", detail="sent via local mock provider")


def _retry_delivery(send_callable, *, channel: str, destination: str) -> DeliveryResult:
    retry_raw = os.getenv("DELIVERY_MAX_RETRIES", "2")
    try:
        attempts = max(1, int(retry_raw))
    except ValueError:
        attempts = 2

    last_error: DeliveryError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return send_callable()
        except DeliveryError as exc:
            last_error = exc
            logger.warning(
                "Delivery attempt %s/%s failed (channel=%s destination=%s): %s",
                attempt,
                attempts,
                channel,
                destination,
                exc,
            )

    raise last_error if last_error else DeliveryError("delivery failed after retries")


def deliver_message(channel: str, phone_number: str, body_text: str, media_url: str | None = None) -> DeliveryResult:
    normalized_channel = "telegram" if channel == "whatsapp" else channel

    if normalized_channel == "telegram":
        provider = os.getenv("DELIVERY_PROVIDER", "mock").lower()
        if provider == "telegram":
            return _retry_delivery(
                lambda: _send_via_telegram(phone_number, body_text, media_url),
                channel=normalized_channel,
                destination=phone_number,
            )
        return _mock_delivery(normalized_channel)

    if normalized_channel == "sms":
        provider = os.getenv("SMS_PROVIDER", "mock").lower()
        if provider == "twilio":
            return _retry_delivery(
                lambda: _send_sms_via_twilio(phone_number, body_text, media_url),
                channel=normalized_channel,
                destination=phone_number,
            )
        return _mock_delivery(normalized_channel)

    raise DeliveryError(f"unsupported channel: {normalized_channel}")
