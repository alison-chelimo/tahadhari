import jwt
import pytest
from fastapi import HTTPException

from app.auth import (
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
    _decode_admin_token,
    create_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_create_access_token_and_decode():
    token = create_access_token("alice")
    assert _decode_admin_token(token) == "alice"


def test_decode_garbage_token_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        _decode_admin_token("not-a-real-token")
    assert exc_info.value.status_code == 401


def test_decode_token_with_wrong_role_raises_401():
    token = jwt.encode({"sub": "alice", "role": "not_admin"}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    with pytest.raises(HTTPException) as exc_info:
        _decode_admin_token(token)
    assert exc_info.value.status_code == 401


def test_decode_expired_token_raises_401():
    from datetime import datetime, timedelta, timezone

    expired_payload = {
        "sub": "alice", "role": "admin",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
    }
    token = jwt.encode(expired_payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    with pytest.raises(HTTPException) as exc_info:
        _decode_admin_token(token)
    assert exc_info.value.status_code == 401
