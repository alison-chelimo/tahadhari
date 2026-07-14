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
    assert body["prompt"] == "awaiting_location"

    rows = db_session.query(RegistrationRequest).all()
    assert len(rows) == 1
    assert rows[0].phone_number == "+254711000020"
    assert rows[0].raw_text == "REGISTER"
    assert rows[0].state == "awaiting_location"


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
    assert response.json() == {
        "matched": False, "registration_request_id": None, "keyword": None, "prompt": None,
    }

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


def _register(client, phone_number: str) -> int:
    response = client.post(
        "/registration/webhook",
        json={"phone_number": phone_number, "channel": "whatsapp", "text": "REGISTER"},
        headers=AUTH_HEADERS,
    )
    return response.json()["registration_request_id"]


def test_webhook_second_message_is_treated_as_location_reply(client, db_session):
    phone_number = "+254711000070"
    request_id = _register(client, phone_number)

    response = client.post(
        "/registration/webhook",
        json={"phone_number": phone_number, "channel": "whatsapp", "text": "Kitengela"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["matched"] is True
    assert body["registration_request_id"] == request_id
    assert body["prompt"] == "location_resolved"

    row = db_session.query(RegistrationRequest).filter(RegistrationRequest.id == request_id).one()
    assert row.state == "location_resolved"
    assert row.raw_location_text == "Kitengela"


def test_webhook_third_message_while_location_resolved_does_not_retrigger(client, db_session):
    phone_number = "+254711000071"
    request_id = _register(client, phone_number)
    client.post(
        "/registration/webhook",
        json={"phone_number": phone_number, "channel": "whatsapp", "text": "Kitengela"},
        headers=AUTH_HEADERS,
    )

    response = client.post(
        "/registration/webhook",
        json={"phone_number": phone_number, "channel": "whatsapp", "text": "anything else"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["prompt"] == "location_resolved"

    row = db_session.query(RegistrationRequest).filter(RegistrationRequest.id == request_id).one()
    assert row.raw_location_text == "Kitengela"  # unchanged, not overwritten


def test_webhook_message_after_terminal_state_does_not_retrigger(client, db_session):
    phone_number = "+254711000072"
    request_id = _register(client, phone_number)
    client.post(
        "/registration/webhook",
        json={"phone_number": phone_number, "channel": "whatsapp", "text": "Kitengela"},
        headers=AUTH_HEADERS,
    )
    client.patch(
        f"/registration/requests/{request_id}/state", json={"state": "weather_delivered"}, headers=AUTH_HEADERS,
    )

    response = client.post(
        "/registration/webhook",
        json={"phone_number": phone_number, "channel": "whatsapp", "text": "thanks"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["prompt"] == "weather_delivered"
    assert response.json()["registration_request_id"] == request_id


def test_profile_creation_mid_conversation_does_not_end_location_flow(client, db_session):
    phone_number = "+254711000073"
    request_id = _register(client, phone_number)

    profile_response = client.post("/profiles/", json=_rural_payload(phone_number), headers=AUTH_HEADERS)
    assert profile_response.status_code == 201
    profile_id = profile_response.json()["id"]

    response = client.post(
        "/registration/webhook",
        json={"phone_number": phone_number, "channel": "whatsapp", "text": "Kitengela"},
        headers=AUTH_HEADERS,
    )
    assert response.json()["prompt"] == "location_resolved"

    row = db_session.query(RegistrationRequest).filter(RegistrationRequest.id == request_id).one()
    assert row.state == "location_resolved"
    assert row.raw_location_text == "Kitengela"
    assert row.profile_id == profile_id  # backfilled by POST /profiles/, conversation unaffected


def test_list_registration_requests_filters_by_state(client, db_session):
    phone_number = "+254711000074"
    request_id = _register(client, phone_number)
    client.post(
        "/registration/webhook",
        json={"phone_number": phone_number, "channel": "whatsapp", "text": "Kitengela"},
        headers=AUTH_HEADERS,
    )

    matching = client.get(
        "/registration/requests", params={"state": "location_resolved"}, headers=AUTH_HEADERS
    )
    assert any(r["id"] == request_id for r in matching.json())

    non_matching = client.get(
        "/registration/requests", params={"state": "awaiting_location"}, headers=AUTH_HEADERS
    )
    assert all(r["id"] != request_id for r in non_matching.json())


def test_patch_registration_request_state_marks_weather_delivered(client, db_session):
    phone_number = "+254711000075"
    request_id = _register(client, phone_number)

    response = client.patch(
        f"/registration/requests/{request_id}/state",
        json={"state": "weather_delivered"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "weather_delivered"
    assert body["resolved_at"] is not None


def test_patch_registration_request_state_marks_failed_without_resolving(client, db_session):
    phone_number = "+254711000076"
    request_id = _register(client, phone_number)

    response = client.patch(
        f"/registration/requests/{request_id}/state", json={"state": "failed"}, headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "failed"
    assert body["resolved_at"] is None


def test_patch_registration_request_state_rejects_invalid_value_422(client, db_session):
    request_id = _register(client, "+254711000077")
    response = client.patch(
        f"/registration/requests/{request_id}/state", json={"state": "bogus"}, headers=AUTH_HEADERS,
    )
    assert response.status_code == 422


def test_patch_registration_request_state_not_found_404(client):
    response = client.patch(
        "/registration/requests/999999/state", json={"state": "failed"}, headers=AUTH_HEADERS,
    )
    assert response.status_code == 404


def test_patch_registration_request_state_requires_credential_401(client):
    response = client.patch("/registration/requests/1/state", json={"state": "failed"})
    assert response.status_code == 401
