import os
from dataclasses import dataclass

import httpx


class DeliveryError(Exception):
    pass


@dataclass
class DeliveryResult:
    provider: str
    provider_message_id: str | None
    detail: str


def _normalize_phone_for_whatsapp(phone_number: str) -> str:
    return "".join(ch for ch in phone_number if ch.isdigit())


def _send_whatsapp_via_meta(phone_number: str, body_text: str, media_url: str | None = None) -> DeliveryResult:
    token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    api_version = os.getenv("WHATSAPP_API_VERSION", "v20.0")
    if not token or not phone_number_id:
        raise DeliveryError("missing WHATSAPP_ACCESS_TOKEN or WHATSAPP_PHONE_NUMBER_ID")

    to_number = _normalize_phone_for_whatsapp(phone_number)
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
    }
    if media_url:
        payload.update({
            "type": "image",
            "image": {"link": media_url, "caption": body_text[:1024]},
        })
    else:
        payload.update({"type": "text", "text": {"body": body_text}})

    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {token}"}
    response = httpx.post(url, json=payload, headers=headers, timeout=15.0)
    if response.status_code >= 400:
        raise DeliveryError(f"Meta WhatsApp API error: {response.status_code} {response.text}")

    data = response.json()
    message_id = None
    messages = data.get("messages")
    if isinstance(messages, list) and messages:
        message_id = messages[0].get("id")
    return DeliveryResult(provider="meta_whatsapp", provider_message_id=message_id, detail="sent via Meta WhatsApp API")


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


def _mock_delivery(channel: str) -> DeliveryResult:
    provider = "mock_whatsapp" if channel == "whatsapp" else "mock_sms"
    return DeliveryResult(provider=provider, provider_message_id="mock-msg-001", detail="sent via local mock provider")


def deliver_message(channel: str, phone_number: str, body_text: str, media_url: str | None = None) -> DeliveryResult:
    if channel == "whatsapp":
        provider = os.getenv("WHATSAPP_PROVIDER", "mock").lower()
        if provider == "meta":
            return _send_whatsapp_via_meta(phone_number, body_text, media_url)
        return _mock_delivery(channel)

    if channel == "sms":
        provider = os.getenv("SMS_PROVIDER", "mock").lower()
        if provider == "twilio":
            return _send_sms_via_twilio(phone_number, body_text, media_url)
        return _mock_delivery(channel)

    raise DeliveryError(f"unsupported channel: {channel}")
