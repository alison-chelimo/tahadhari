from app.auth import SERVICE_API_KEY
from app.models import RegistrationRequest

AUTH_HEADERS = {"X-API-Key": SERVICE_API_KEY}


def _rural_payload(phone_number: str) -> dict:
    return {
        "phone_number": phone_number, "channel": "whatsapp", "user_type": "rural",
        "occupation": "farmer", "ward": "Kisumu_Central", "key_asset": "maize_farm",
        "registration_source": "whatsapp_keyword",
    }


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


def test_webhook_matched_keyword_with_trailing_punctuation(client, db_session):
    texts = ["Register.", "REGISTER!", "register-now"]
    for i, text in enumerate(texts):
        response = client.post(
            "/registration/webhook",
            json={"phone_number": f"+25471100003{i}", "channel": "sms", "text": text},
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["matched"] is True, f"expected {text!r} to match"


def test_webhook_leading_punctuation_still_unmatched(client, db_session):
    response = client.post(
        "/registration/webhook",
        json={"phone_number": "+254711000040", "channel": "sms", "text": "registeringmybusiness"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["matched"] is False


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


def test_webhook_retry_deduplicates_pending_request(client, db_session):
    phone_number = "+254711000024"
    first = client.post(
        "/registration/webhook",
        json={"phone_number": phone_number, "channel": "sms", "text": "REGISTER"},
        headers=AUTH_HEADERS,
    )
    retry = client.post(
        "/registration/webhook",
        json={"phone_number": phone_number, "channel": "sms", "text": "REGISTER"},
        headers=AUTH_HEADERS,
    )
    assert first.json()["registration_request_id"] == retry.json()["registration_request_id"]
    assert db_session.query(RegistrationRequest).filter(
        RegistrationRequest.phone_number == phone_number
    ).count() == 1


def test_profile_creation_resolves_pending_registration_request(client, db_session):
    phone_number = "+254711000025"
    webhook_response = client.post(
        "/registration/webhook",
        json={"phone_number": phone_number, "channel": "whatsapp", "text": "REGISTER"},
        headers=AUTH_HEADERS,
    )
    request_id = webhook_response.json()["registration_request_id"]

    pending = client.get("/registration/requests", params={"resolved": False}, headers=AUTH_HEADERS)
    assert any(r["id"] == request_id for r in pending.json())

    profile_response = client.post("/profiles/", json=_rural_payload(phone_number), headers=AUTH_HEADERS)
    assert profile_response.status_code == 201
    profile_id = profile_response.json()["id"]

    resolved = client.get("/registration/requests", params={"resolved": True}, headers=AUTH_HEADERS)
    resolved_row = next(r for r in resolved.json() if r["id"] == request_id)
    assert resolved_row["profile_id"] == profile_id
    assert resolved_row["resolved_at"] is not None

    still_pending = client.get("/registration/requests", params={"resolved": False}, headers=AUTH_HEADERS)
    assert all(r["id"] != request_id for r in still_pending.json())


def test_list_registration_requests_requires_credential_401(client):
    response = client.get("/registration/requests")
    assert response.status_code == 401
