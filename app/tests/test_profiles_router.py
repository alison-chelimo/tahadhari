from app.auth import SERVICE_API_KEY
from app.models import Profile

AUTH_HEADERS = {"X-API-Key": SERVICE_API_KEY}


def _rural_payload(phone_number: str = "+254711000001") -> dict:
    return {
        "phone_number": phone_number, "channel": "whatsapp", "user_type": "rural",
        "occupation": "farmer", "ward": "Kisumu_Central", "key_asset": "maize_farm",
        "registration_source": "whatsapp_keyword",
    }


def _urban_payload(phone_number: str = "+254711000002") -> dict:
    return {
        "phone_number": phone_number, "channel": "sms", "user_type": "urban",
        "route_id": "Adams_Arcade", "registration_source": "sms_keyword",
    }


def _partner_payload(phone_number: str = "+254711000003") -> dict:
    return {
        "phone_number": phone_number, "channel": "whatsapp", "user_type": "rural",
        "occupation": "fisherman", "ward": "Kisumu_Central", "key_asset": "fishing_boat",
        "registration_source": "partner_assisted", "registered_by": "CHW Jane Doe",
    }


def test_create_profile_rural_success(client):
    response = client.post("/profiles/", json=_rural_payload(), headers=AUTH_HEADERS)
    assert response.status_code == 201
    body = response.json()
    assert body["user_type"] == "rural"
    assert body["ward"] == "Kisumu_Central"
    assert body["registration_source"] == "whatsapp_keyword"


def test_create_profile_urban_success(client):
    response = client.post("/profiles/", json=_urban_payload(), headers=AUTH_HEADERS)
    assert response.status_code == 201
    body = response.json()
    assert body["user_type"] == "urban"
    assert body["route_id"] == "Adams_Arcade"


def test_create_profile_partner_assisted_success(client):
    response = client.post("/profiles/", json=_partner_payload(), headers=AUTH_HEADERS)
    assert response.status_code == 201
    body = response.json()
    assert body["registration_source"] == "partner_assisted"
    assert body["registered_by"] == "CHW Jane Doe"


def test_create_profile_partner_assisted_missing_registered_by_422(client):
    payload = _partner_payload()
    del payload["registered_by"]
    response = client.post("/profiles/", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 422


def test_create_profile_rural_missing_ward_422(client):
    payload = _rural_payload()
    del payload["ward"]
    response = client.post("/profiles/", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 422


def test_create_profile_rural_missing_occupation_422(client):
    payload = _rural_payload()
    del payload["occupation"]
    response = client.post("/profiles/", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 422


def test_create_profile_urban_missing_route_id_422(client):
    payload = _urban_payload()
    del payload["route_id"]
    response = client.post("/profiles/", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 422


def test_create_profile_urban_invalid_route_id_pattern_422(client):
    payload = _urban_payload()
    payload["route_id"] = "Adams Arcade"
    response = client.post("/profiles/", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 422


def test_create_profile_duplicate_phone_number_409(client):
    payload = _rural_payload(phone_number="+254711000099")
    first = client.post("/profiles/", json=payload, headers=AUTH_HEADERS)
    assert first.status_code == 201
    second = client.post("/profiles/", json=payload, headers=AUTH_HEADERS)
    assert second.status_code == 409


def test_create_profile_requires_credential_401(client):
    response = client.post("/profiles/", json=_rural_payload())
    assert response.status_code == 401


def test_get_profile_success(client, db_session):
    profile = Profile(
        phone_number="+254711000010", channel="whatsapp", user_type="rural",
        occupation="farmer", ward="Kisumu_Central", registration_source="whatsapp_keyword",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)

    response = client.get(f"/profiles/{profile.id}", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json()["id"] == profile.id


def test_get_profile_not_found_404(client):
    response = client.get("/profiles/999", headers=AUTH_HEADERS)
    assert response.status_code == 404


def test_get_profile_requires_credential_401(client):
    response = client.get("/profiles/1")
    assert response.status_code == 401


def test_list_profiles_success(client):
    client.post("/profiles/", json=_rural_payload(), headers=AUTH_HEADERS)
    client.post("/profiles/", json=_urban_payload(), headers=AUTH_HEADERS)

    response = client.get("/profiles/", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_profiles_requires_credential_401(client):
    response = client.get("/profiles/")
    assert response.status_code == 401
