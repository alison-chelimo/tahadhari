from app.auth import SERVICE_API_KEY
from app.models import Alert, Message, Profile

AUTH_HEADERS = {"X-API-Key": SERVICE_API_KEY}


def _make_profile(db_session, channel: str = "whatsapp") -> Profile:
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


def test_send_message_updates_status_to_sent_with_mock_provider(client, db_session):
    profile = _make_profile(db_session, channel="whatsapp")
    message = _make_message(db_session, profile, channel="whatsapp")

    response = client.post(
        f"/delivery/messages/{message.id}/send",
        json={},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["delivery_status"] == "sent"
    assert body["provider"] == "mock_whatsapp"

    db_session.refresh(message)
    assert message.delivery_status == "sent"


def test_send_message_can_force_sms_channel(client, db_session):
    profile = _make_profile(db_session, channel="whatsapp")
    message = _make_message(db_session, profile, channel="whatsapp")

    response = client.post(
        f"/delivery/messages/{message.id}/send",
        json={"force_channel": "sms"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["channel"] == "sms"
    assert body["provider"] == "mock_sms"


def test_send_message_not_found_404(client):
    response = client.post("/delivery/messages/999/send", json={}, headers=AUTH_HEADERS)
    assert response.status_code == 404


def test_send_message_requires_auth(client):
    response = client.post("/delivery/messages/1/send", json={})
    assert response.status_code == 401
