import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

_bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
_INVALID_TOKEN = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": username, "role": "admin", "exp": expire}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def _decode_admin_token(token: str) -> str:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise _INVALID_TOKEN
    if payload.get("role") != "admin" or "sub" not in payload:
        raise _INVALID_TOKEN
    return payload["sub"]


def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """Strictly admin-only: a valid admin JWT, nothing else satisfies this."""
    if credentials is None:
        raise _UNAUTHORIZED
    return _decode_admin_token(credentials.credentials)


def require_service_or_admin(
    x_api_key: str | None = Header(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """Machine tier: the shared service API key OR a valid admin JWT (the admin is a
    strict superset of trust, so a logged-in admin can also hit these routes)."""
    if x_api_key and SERVICE_API_KEY and x_api_key == SERVICE_API_KEY:
        return "service"
    if credentials is not None:
        return _decode_admin_token(credentials.credentials)
    raise _UNAUTHORIZED
