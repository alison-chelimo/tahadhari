from app.auth import SERVICE_API_KEY, create_access_token
from app.models import Alert, Message, Profile
from .conftest import ADMIN_PASSWORD


def test_login_success(client, admin_user):
    response = client.post("/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_login_wrong_password(client, admin_user):
    response = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 401


def test_login_unknown_user(client):
    response = client.post("/auth/login", json={"username": "nobody", "password": "x"})
    assert response.status_code == 401


def _match_params():
    return {"hazard_type": "heavy_rainfall", "occupation": "farmer", "severity": "high", "language": "en"}


def test_service_tier_route_requires_credential(client, admin_user):
    no_creds = client.get("/templates/match", params=_match_params())
    assert no_creds.status_code == 401

    with_key = client.get("/templates/match", params=_match_params(), headers={"X-API-Key": SERVICE_API_KEY})
    assert with_key.status_code == 200

    token = create_access_token(admin_user.username)
    with_jwt = client.get(
        "/templates/match", params=_match_params(), headers={"Authorization": f"Bearer {token}"}
    )
    assert with_jwt.status_code == 200


def test_admin_only_route_rejects_service_key(client):
    payload = {
        "hazard_type": "heavy_rainfall", "occupation": "farmer",
        "severity": "high", "language": "en", "template_text": "Rain expected in {ward}.",
    }
    response = client.post("/templates/", json=payload, headers={"X-API-Key": SERVICE_API_KEY})
    assert response.status_code == 401


def test_alert_get_stays_public(client):
    ingest = client.post(
        "/alerts/ingest",
        json={"source": "test", "geography_type": "ward", "geography_ref": "Kisumu_Central", "rainfall_mm": 65.0},
        headers={"X-API-Key": SERVICE_API_KEY},
    )
    assert ingest.status_code == 200
    alert_id = ingest.json()["id"]

    public_read = client.get(f"/alerts/{alert_id}")
    assert public_read.status_code == 200


def test_feedback_rejects_profile_mismatch(client, db_session):
    profile_a = Profile(phone_number="+254700000001", channel="whatsapp", language="en", user_type="rural")
    profile_b = Profile(phone_number="+254700000002", channel="whatsapp", language="en", user_type="rural")
    db_session.add_all([profile_a, profile_b])
    db_session.commit()

    alert = Alert(hazard_type="heavy_rainfall", severity="high", geography_type="ward", geography_ref="Kisumu_Central", rainfall_mm=65.0)
    db_session.add(alert)
    db_session.commit()

    message = Message(profile_id=profile_a.id, alert_id=alert.id, final_text="test", channel="whatsapp")
    db_session.add(message)
    db_session.commit()

    response = client.post(
        "/feedback/",
        json={"message_id": message.id, "profile_id": profile_b.id, "feedback_type": "helpful"},
        headers={"X-API-Key": SERVICE_API_KEY},
    )
    assert response.status_code == 400
