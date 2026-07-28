import os


def _post_update(
    client,
    text: str,
    chat_id: int = 123456789,
    headers: dict | None = None,
    include_secret_header: bool = True,
):
    payload = {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "chat": {"id": chat_id, "type": "private"},
            "date": 1700000000,
            "text": text,
        },
    }
    effective_headers = dict(headers or {})
    expected_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if include_secret_header and expected_secret and "X-Telegram-Bot-Api-Secret-Token" not in effective_headers:
        effective_headers["X-Telegram-Bot-Api-Secret-Token"] = expected_secret
    return client.post("/telegram/webhook", json=payload, headers=effective_headers)


def _post_callback(
    client,
    data: str,
    chat_id: int = 123456789,
    headers: dict | None = None,
    include_secret_header: bool = True,
):
    payload = {
        "update_id": 2,
        "callback_query": {
            "id": "cbq-1",
            "from": {"id": chat_id, "is_bot": False, "first_name": "Test"},
            "message": {
                "message_id": 11,
                "chat": {"id": chat_id, "type": "private"},
                "date": 1700000001,
                "text": "prompt",
            },
            "data": data,
        },
    }
    effective_headers = dict(headers or {})
    expected_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if include_secret_header and expected_secret and "X-Telegram-Bot-Api-Secret-Token" not in effective_headers:
        effective_headers["X-Telegram-Bot-Api-Secret-Token"] = expected_secret
    return client.post("/telegram/webhook", json=payload, headers=effective_headers)


def test_telegram_webhook_start_and_rural_flow(client, db_session, monkeypatch):
    sent = []

    def fake_send(chat_id: str, text: str, reply_markup=None):
        sent.append((chat_id, text, reply_markup))

    monkeypatch.setattr("app.routers.telegram._send_telegram_text", fake_send)

    r = _post_update(client, "/start", chat_id=111)
    assert r.status_code == 200
    assert r.json()["detail"] == "started"
    assert sent[-1][0] == "111"
    assert "select your county" in sent[-1][1].casefold()
    assert sent[-1][2] is not None
    assert "inline_keyboard" in sent[-1][2]

    r = _post_update(client, "Kiambu", chat_id=111)
    assert r.status_code == 200
    assert r.json()["detail"] == "advanced"

    r = _post_update(client, "Thika", chat_id=111)
    assert r.status_code == 200
    assert r.json()["detail"] == "advanced"

    r = _post_callback(client, "occupation:Farmer", chat_id=111)
    assert r.status_code == 200
    assert r.json()["detail"] == "advanced"

    r = _post_update(client, "Maize farm", chat_id=111)
    assert r.status_code == 200
    body = r.json()
    assert body["detail"] == "registered"
    assert "profile_id" in body

    from app.models import Profile

    profile = db_session.query(Profile).filter(Profile.phone_number == "111").first()
    assert profile is not None
    assert profile.channel == "telegram"
    assert profile.user_type == "rural"
    assert profile.ward == "Thika, Kiambu"
    assert profile.occupation == "Farmer"
    assert profile.key_asset == "Maize farm"
    assert profile.route_id is None


def test_telegram_webhook_invalid_county_then_recover(client, db_session, monkeypatch):
    sent = []

    def fake_send(chat_id: str, text: str, reply_markup=None):
        sent.append((chat_id, text, reply_markup))

    monkeypatch.setattr("app.routers.telegram._send_telegram_text", fake_send)

    r = _post_update(client, "/start", chat_id=222)
    assert r.status_code == 200

    r = _post_update(client, "Atlantis", chat_id=222)
    assert r.status_code == 200
    assert r.json()["detail"] == "invalid_county"

    r = _post_update(client, "Nakuru", chat_id=222)
    assert r.status_code == 200
    assert r.json()["detail"] == "advanced"

    r = _post_update(client, "Naivasha", chat_id=222)
    assert r.status_code == 200
    assert r.json()["detail"] == "advanced"

    r = _post_callback(client, "occupation:Market trader", chat_id=222)
    assert r.status_code == 200
    assert r.json()["detail"] == "advanced"

    r = _post_update(client, "Shop stock", chat_id=222)
    assert r.status_code == 200
    assert r.json()["detail"] == "registered"

    from app.models import Profile

    profile = db_session.query(Profile).filter(Profile.phone_number == "222").first()
    assert profile is not None
    assert profile.user_type == "rural"
    assert profile.route_id is None
    assert profile.ward == "Naivasha, Nakuru"
    assert profile.occupation == "Market trader"
    assert profile.key_asset == "Shop stock"


def test_telegram_webhook_callback_buttons_flow(client, db_session, monkeypatch):
    sent = []

    def fake_send(chat_id: str, text: str, reply_markup=None):
        sent.append((chat_id, text, reply_markup))

    monkeypatch.setattr("app.routers.telegram._send_telegram_text", fake_send)
    monkeypatch.setattr("app.routers.telegram._answer_telegram_callback", lambda callback_query_id: None)

    r = _post_update(client, "/start", chat_id=223)
    assert r.status_code == 200
    assert r.json()["detail"] == "started"

    r = _post_callback(client, "county:Nakuru", chat_id=223)
    assert r.status_code == 200
    assert r.json()["detail"] == "advanced"

    r = _post_callback(client, "town:Naivasha", chat_id=223)
    assert r.status_code == 200
    assert r.json()["detail"] == "advanced"

    r = _post_callback(client, "occupation:Market trader", chat_id=223)
    assert r.status_code == 200
    assert r.json()["detail"] == "advanced"

    r = _post_update(client, "Shop stock", chat_id=223)
    assert r.status_code == 200
    assert r.json()["detail"] == "registered"

    from app.models import Profile

    profile = db_session.query(Profile).filter(Profile.phone_number == "223").first()
    assert profile is not None
    assert profile.ward == "Naivasha, Nakuru"


def test_telegram_webhook_invalid_occupation_requires_button_choice(client, monkeypatch):
    sent = []

    def fake_send(chat_id: str, text: str, reply_markup=None):
        sent.append((chat_id, text, reply_markup))

    monkeypatch.setattr("app.routers.telegram._send_telegram_text", fake_send)

    r = _post_update(client, "/start", chat_id=224)
    assert r.status_code == 200
    assert r.json()["detail"] == "started"

    r = _post_callback(client, "county:Kiambu", chat_id=224)
    assert r.status_code == 200
    assert r.json()["detail"] == "advanced"

    r = _post_callback(client, "town:Thika", chat_id=224)
    assert r.status_code == 200
    assert r.json()["detail"] == "advanced"

    r = _post_update(client, "Astronaut", chat_id=224)
    assert r.status_code == 200
    assert r.json()["detail"] == "invalid_occupation"
    assert "Invalid occupation" in sent[-1][1]
    assert sent[-1][2] is not None
    assert "inline_keyboard" in sent[-1][2]


def test_telegram_webhook_requires_secret_when_configured(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "super-secret")

    r = _post_update(client, "/start", chat_id=333, include_secret_header=False)
    assert r.status_code == 401

    r = _post_update(
        client,
        "/start",
        chat_id=333,
        headers={"X-Telegram-Bot-Api-Secret-Token": "super-secret"},
    )
    assert r.status_code == 200
    assert r.json()["detail"] == "started"


def test_telegram_webhook_ignores_non_text_updates(client):
    payload = {
        "update_id": 2,
        "message": {
            "message_id": 11,
            "chat": {"id": 444, "type": "private"},
            "date": 1700000001,
        },
    }

    effective_headers = {}
    expected_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if expected_secret:
        effective_headers["X-Telegram-Bot-Api-Secret-Token"] = expected_secret

    r = client.post("/telegram/webhook", json=payload, headers=effective_headers)
    assert r.status_code == 200
    assert r.json()["detail"] == "ignored"


def test_telegram_webhook_start_does_not_reregister_existing_profile(client, db_session, monkeypatch):
    sent = []

    def fake_send(chat_id: str, text: str, reply_markup=None):
        sent.append((chat_id, text, reply_markup))

    monkeypatch.setattr("app.routers.telegram._send_telegram_text", fake_send)

    from app.models import Profile

    profile = Profile(
        phone_number="555",
        channel="telegram",
        language="en",
        user_type="rural",
        occupation="Farmer",
        ward="Mlandizi",
        key_asset="Maize farm",
        registration_source="partner_assisted",
        registered_by="telegram_bot",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)

    r = _post_update(client, "/start", chat_id=555)
    assert r.status_code == 200
    body = r.json()
    assert body["detail"] == "already_registered"
    assert body["profile_id"] == profile.id
    assert "already registered" in sent[-1][1]


def test_telegram_webhook_allows_occupation_amend_only(client, db_session, monkeypatch):
    sent = []

    def fake_send(chat_id: str, text: str, reply_markup=None):
        sent.append((chat_id, text, reply_markup))

    monkeypatch.setattr("app.routers.telegram._send_telegram_text", fake_send)

    from app.models import Profile

    profile = Profile(
        phone_number="556",
        channel="telegram",
        language="en",
        user_type="rural",
        occupation="Farmer",
        ward="Mlandizi",
        key_asset="Maize farm",
        registration_source="partner_assisted",
        registered_by="telegram_bot",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)

    r = _post_update(client, "/occupation", chat_id=556)
    assert r.status_code == 200
    assert r.json()["detail"] == "await_occupation_amend"

    r = _post_update(client, "Teacher", chat_id=556)
    assert r.status_code == 200
    body = r.json()
    assert body["detail"] == "occupation_updated"
    assert body["profile_id"] == profile.id

    db_session.expire_all()
    updated = db_session.query(Profile).filter(Profile.id == profile.id).first()
    assert updated is not None
    assert updated.occupation == "Teacher"


def test_telegram_webhook_occupation_amend_requires_registration(client, monkeypatch):
    sent = []

    def fake_send(chat_id: str, text: str, reply_markup=None):
        sent.append((chat_id, text, reply_markup))

    monkeypatch.setattr("app.routers.telegram._send_telegram_text", fake_send)

    r = _post_update(client, "/occupation", chat_id=557)
    assert r.status_code == 200
    assert r.json()["detail"] == "not_registered"
    assert "not registered yet" in sent[-1][1]


def test_telegram_webhook_routes_registered_free_text_to_ai(client, db_session, monkeypatch):
    sent = []

    def fake_send(chat_id: str, text: str, reply_markup=None):
        sent.append((chat_id, text, reply_markup))

    monkeypatch.setattr("app.routers.telegram._send_telegram_text", fake_send)
    monkeypatch.setattr("app.routers.telegram._generate_ai_reply_sync", lambda profile, user_text: "AI reply")

    from app.models import Profile

    profile = Profile(
        phone_number="558",
        channel="telegram",
        language="en",
        user_type="rural",
        occupation="Farmer",
        ward="Mlandizi",
        key_asset="Maize farm",
        registration_source="partner_assisted",
        registered_by="telegram_bot",
    )
    db_session.add(profile)
    db_session.commit()

    r = _post_update(client, "How can I protect my farm this week?", chat_id=558)
    assert r.status_code == 200
    body = r.json()
    assert body["detail"] == "ai_reply_sent"
    assert body["profile_id"] == profile.id
    assert sent[-1] == ("558", "AI reply", None)


def test_telegram_webhook_registered_unknown_command(client, db_session, monkeypatch):
    sent = []

    def fake_send(chat_id: str, text: str, reply_markup=None):
        sent.append((chat_id, text, reply_markup))

    monkeypatch.setattr("app.routers.telegram._send_telegram_text", fake_send)

    from app.models import Profile

    profile = Profile(
        phone_number="559",
        channel="telegram",
        language="en",
        user_type="rural",
        occupation="Farmer",
        ward="Mlandizi",
        key_asset="Maize farm",
        registration_source="partner_assisted",
        registered_by="telegram_bot",
    )
    db_session.add(profile)
    db_session.commit()

    r = _post_update(client, "/weather", chat_id=559)
    assert r.status_code == 200
    body = r.json()
    assert body["detail"] == "unknown_command"
    assert body["profile_id"] == profile.id
    assert "Unknown command" in sent[-1][1]


def test_telegram_webhook_resetme_enabled_resets_profile(client, db_session, monkeypatch):
    sent = []

    def fake_send(chat_id: str, text: str, reply_markup=None):
        sent.append((chat_id, text, reply_markup))

    monkeypatch.setattr("app.routers.telegram._send_telegram_text", fake_send)
    monkeypatch.setenv("TELEGRAM_ENABLE_DEV_RESET", "true")

    from app.models import Profile

    profile = Profile(
        phone_number="560",
        channel="telegram",
        language="en",
        user_type="rural",
        occupation="Farmer",
        ward="Mlandizi",
        key_asset="Maize farm",
        registration_source="partner_assisted",
        registered_by="telegram_bot",
    )
    db_session.add(profile)
    db_session.commit()

    r = _post_update(client, "/resetme", chat_id=560)
    assert r.status_code == 200
    assert r.json()["detail"] == "reset_done"
    assert "reset complete" in sent[-1][1]

    deleted = db_session.query(Profile).filter(Profile.phone_number == "560").first()
    assert deleted is None


def test_telegram_webhook_resetme_disabled(client, db_session, monkeypatch):
    sent = []

    def fake_send(chat_id: str, text: str, reply_markup=None):
        sent.append((chat_id, text, reply_markup))

    monkeypatch.setattr("app.routers.telegram._send_telegram_text", fake_send)
    monkeypatch.delenv("TELEGRAM_ENABLE_DEV_RESET", raising=False)

    r = _post_update(client, "/resetme", chat_id=561)
    assert r.status_code == 200
    assert r.json()["detail"] == "reset_disabled"
    assert "disabled" in sent[-1][1]
