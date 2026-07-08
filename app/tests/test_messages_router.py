from app.auth import SERVICE_API_KEY
from app.models import ActionTemplate, Alert, FloodPrediction, Message, Profile, RoadSegment

AUTH_HEADERS = {"X-API-Key": SERVICE_API_KEY}


def _make_profile(db_session) -> Profile:
    profile = Profile(
        phone_number="+254700000010", channel="whatsapp", language="en", user_type="rural",
        registration_source="partner_assisted", registered_by="test",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return profile


def _make_alert(db_session) -> Alert:
    alert = Alert(
        hazard_type="heavy_rainfall", severity="high",
        geography_type="ward", geography_ref="Kisumu_Central", rainfall_mm=65.0,
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)
    return alert


def test_create_message_success(client, db_session):
    profile = _make_profile(db_session)
    alert = _make_alert(db_session)

    response = client.post(
        "/messages/",
        json={
            "profile_id": profile.id, "alert_id": alert.id,
            "final_text": "Heavy rain expected.", "channel": "whatsapp",
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["profile_id"] == profile.id
    assert body["alert_id"] == alert.id
    assert body["delivery_status"] == "pending"


def test_create_message_requires_credential(client, db_session):
    profile = _make_profile(db_session)
    alert = _make_alert(db_session)

    response = client.post(
        "/messages/",
        json={"profile_id": profile.id, "alert_id": alert.id, "final_text": "hi", "channel": "whatsapp"},
    )
    assert response.status_code == 401


def test_create_message_missing_profile_404(client, db_session):
    alert = _make_alert(db_session)
    response = client.post(
        "/messages/",
        json={"profile_id": 999, "alert_id": alert.id, "final_text": "hi", "channel": "whatsapp"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 404
    assert "Profile" in response.json()["detail"]


def test_create_message_missing_alert_404(client, db_session):
    profile = _make_profile(db_session)
    response = client.post(
        "/messages/",
        json={"profile_id": profile.id, "alert_id": 999, "final_text": "hi", "channel": "whatsapp"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 404
    assert "Alert" in response.json()["detail"]


def test_create_message_missing_template_404(client, db_session):
    profile = _make_profile(db_session)
    alert = _make_alert(db_session)
    response = client.post(
        "/messages/",
        json={
            "profile_id": profile.id, "alert_id": alert.id, "template_id": 999,
            "final_text": "hi", "channel": "whatsapp",
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 404
    assert "ActionTemplate" in response.json()["detail"]


def test_create_message_missing_flood_prediction_404(client, db_session):
    profile = _make_profile(db_session)
    alert = _make_alert(db_session)
    response = client.post(
        "/messages/",
        json={
            "profile_id": profile.id, "alert_id": alert.id, "flood_prediction_id": 999,
            "final_text": "hi", "channel": "whatsapp",
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 404
    assert "FloodPrediction" in response.json()["detail"]


def test_create_message_with_template_and_flood_prediction_success(client, db_session):
    profile = _make_profile(db_session)
    alert = _make_alert(db_session)
    template = ActionTemplate(
        hazard_type="heavy_rainfall", occupation="farmer", severity="high",
        language="en", template_text="Rain expected in {ward}.",
    )
    segment = RoadSegment(
        corridor_name="Ngong_Road", segment_name="Adams_Arcade", drainage_capacity_mm=50.0,
    )
    db_session.add_all([template, segment])
    db_session.commit()
    db_session.refresh(template)
    db_session.refresh(segment)

    prediction = FloodPrediction(alert_id=alert.id, segment_id=segment.id, risk_level="high")
    db_session.add(prediction)
    db_session.commit()
    db_session.refresh(prediction)

    response = client.post(
        "/messages/",
        json={
            "profile_id": profile.id, "alert_id": alert.id, "template_id": template.id,
            "flood_prediction_id": prediction.id, "final_text": "hi", "channel": "whatsapp",
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["template_id"] == template.id
    assert body["flood_prediction_id"] == prediction.id


def test_get_message_success(client, db_session):
    profile = _make_profile(db_session)
    alert = _make_alert(db_session)
    message = Message(profile_id=profile.id, alert_id=alert.id, final_text="hi", channel="whatsapp")
    db_session.add(message)
    db_session.commit()
    db_session.refresh(message)

    response = client.get(f"/messages/{message.id}", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json()["id"] == message.id


def test_get_message_not_found(client, db_session):
    response = client.get("/messages/999", headers=AUTH_HEADERS)
    assert response.status_code == 404
