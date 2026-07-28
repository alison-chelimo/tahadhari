from app.auth import SERVICE_API_KEY
from app.models import Alert, Message, Profile
from app.services import delivery

AUTH_HEADERS = {"X-API-Key": SERVICE_API_KEY}


def _set_default_delivery_env(monkeypatch):
    monkeypatch.setenv("DELIVERY_PROVIDER", "mock")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)


def _make_profile(db_session, channel: str = "telegram") -> Profile:
    profile = Profile(
        phone_number="+254700111000",
        channel=channel,
        language="en",
        user_type="rural",
        occupation="farmer",
        ward="Kisumu_Central",
        key_asset="maize_farm",
        registration_source="partner_assisted",
        registered_by="test",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return profile


def _make_message(db_session, profile: Profile, channel: str) -> Message:
    alert = Alert(
        hazard_type="heavy_rainfall",
        severity="high",
        geography_type="ward",
        geography_ref="Kisumu_Central",
        rainfall_mm=67.0,
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    message = Message(
        profile_id=profile.id,
        alert_id=alert.id,
        final_text="Heavy rainfall expected. Move livestock to higher ground.",
        channel=channel,
    )
    db_session.add(message)
    db_session.commit()
    db_session.refresh(message)
    return message


def test_send_message_updates_status_to_sent_with_mock_provider(client, db_session, monkeypatch):
    _set_default_delivery_env(monkeypatch)
    profile = _make_profile(db_session, channel="telegram")
    message = _make_message(db_session, profile, channel="telegram")

    response = client.post(
        f"/delivery/messages/{message.id}/send",
        json={},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["delivery_status"] == "sent"
    assert body["provider"] == "mock_telegram"

    db_session.refresh(message)
    assert message.delivery_status == "sent"


def test_send_message_can_force_sms_channel(client, db_session, monkeypatch):
    _set_default_delivery_env(monkeypatch)
    profile = _make_profile(db_session, channel="telegram")
    message = _make_message(db_session, profile, channel="telegram")

    response = client.post(
        f"/delivery/messages/{message.id}/send",
        json={"force_channel": "sms"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["channel"] == "sms"
    assert body["provider"] == "mock_sms"


def test_send_message_not_found_404(client, monkeypatch):
    _set_default_delivery_env(monkeypatch)
    response = client.post("/delivery/messages/999/send", json={}, headers=AUTH_HEADERS)
    assert response.status_code == 404


def test_send_message_requires_auth(client):
    response = client.post("/delivery/messages/1/send", json={})
    assert response.status_code == 401


def test_send_message_telegram_provider_success(client, db_session, monkeypatch):
    profile = _make_profile(db_session, channel="telegram")
    profile.phone_number = "123456789"
    db_session.commit()
    message = _make_message(db_session, profile, channel="telegram")

    monkeypatch.setenv("DELIVERY_PROVIDER", "telegram")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-bot-token")

    class _Resp:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"ok": True, "result": {"message_id": 9876}}

    monkeypatch.setattr(delivery.httpx, "post", lambda *args, **kwargs: _Resp())

    response = client.post(
        f"/delivery/messages/{message.id}/send",
        json={},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["delivery_status"] == "sent"
    assert body["provider"] == "telegram"


def test_send_message_telegram_provider_missing_token_fails(client, db_session, monkeypatch):
    profile = _make_profile(db_session, channel="telegram")
    profile.phone_number = "123456789"
    db_session.commit()
    message = _make_message(db_session, profile, channel="telegram")

    monkeypatch.setenv("DELIVERY_PROVIDER", "telegram")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    response = client.post(
        f"/delivery/messages/{message.id}/send",
        json={},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["delivery_status"] == "failed"
    assert "TELEGRAM_BOT_TOKEN" in body["detail"]
