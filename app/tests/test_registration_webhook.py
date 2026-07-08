from app.auth import SERVICE_API_KEY
from app.models import RegistrationRequest

AUTH_HEADERS = {"X-API-Key": SERVICE_API_KEY}


def test_webhook_matched_keyword_creates_registration_request(client, db_session):
    response = client.post(
        "/registration/webhook",
        json={"phone_number": "+254711000020", "channel": "sms", "text": "REGISTER"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["matched"] is True
    assert body["keyword"] == "register"
    assert body["registration_request_id"] is not None

    rows = db_session.query(RegistrationRequest).all()
    assert len(rows) == 1
    assert rows[0].phone_number == "+254711000020"
    assert rows[0].raw_text == "REGISTER"


def test_webhook_matched_keyword_case_insensitive_with_trailing_text(client, db_session):
    response = client.post(
        "/registration/webhook",
        json={"phone_number": "+254711000021", "channel": "whatsapp", "text": "register please help"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["matched"] is True

    rows = db_session.query(RegistrationRequest).all()
    assert len(rows) == 1
    assert rows[0].matched_keyword == "register"


def test_webhook_unmatched_text_no_row_created(client, db_session):
    response = client.post(
        "/registration/webhook",
        json={"phone_number": "+254711000022", "channel": "sms", "text": "hello there"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json() == {"matched": False, "registration_request_id": None, "keyword": None}

    assert db_session.query(RegistrationRequest).count() == 0


def test_webhook_requires_credential_401(client):
    response = client.post(
        "/registration/webhook",
        json={"phone_number": "+254711000023", "channel": "sms", "text": "REGISTER"},
    )
    assert response.status_code == 401
