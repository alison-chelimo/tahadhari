from app.auth import SERVICE_API_KEY
from app.models import Alert, Feedback, Message, Profile

AUTH_HEADERS = {"X-API-Key": SERVICE_API_KEY}


def _make_profile(db_session, phone="+254700000020") -> Profile:
    profile = Profile(
        phone_number=phone, channel="whatsapp", language="en", user_type="rural",
        registration_source="partner_assisted", registered_by="test",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return profile


def _make_message(db_session, profile: Profile) -> Message:
    alert = Alert(
        hazard_type="heavy_rainfall", severity="high",
        geography_type="ward", geography_ref="Kisumu_Central", rainfall_mm=65.0,
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    message = Message(profile_id=profile.id, alert_id=alert.id, final_text="hi", channel="whatsapp")
    db_session.add(message)
    db_session.commit()
    db_session.refresh(message)
    return message


def test_create_feedback_success(client, db_session):
    profile = _make_profile(db_session)
    message = _make_message(db_session, profile)

    response = client.post(
        "/feedback/",
        json={"message_id": message.id, "profile_id": profile.id, "feedback_type": "helpful"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["message_id"] == message.id
    assert body["profile_id"] == profile.id
    assert body["feedback_type"] == "helpful"


def test_create_feedback_requires_credential(client, db_session):
    profile = _make_profile(db_session)
    message = _make_message(db_session, profile)

    response = client.post(
        "/feedback/",
        json={"message_id": message.id, "profile_id": profile.id, "feedback_type": "helpful"},
    )
    assert response.status_code == 401


def test_create_feedback_missing_message_404(client, db_session):
    profile = _make_profile(db_session)
    response = client.post(
        "/feedback/",
        json={"message_id": 999, "profile_id": profile.id, "feedback_type": "helpful"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 404
    assert "Message" in response.json()["detail"]


def test_create_feedback_missing_profile_404(client, db_session):
    profile = _make_profile(db_session)
    message = _make_message(db_session, profile)
    response = client.post(
        "/feedback/",
        json={"message_id": message.id, "profile_id": 999, "feedback_type": "helpful"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 404
    assert "Profile" in response.json()["detail"]


def test_get_feedback_success(client, db_session):
    profile = _make_profile(db_session)
    message = _make_message(db_session, profile)
    feedback = Feedback(message_id=message.id, profile_id=profile.id, feedback_type="helpful")
    db_session.add(feedback)
    db_session.commit()
    db_session.refresh(feedback)

    response = client.get(f"/feedback/{feedback.id}", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json()["id"] == feedback.id


def test_get_feedback_not_found(client, db_session):
    response = client.get("/feedback/999", headers=AUTH_HEADERS)
    assert response.status_code == 404
