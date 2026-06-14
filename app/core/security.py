import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import Response
from jose import jwt

from app.core.config import settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        seconds=settings.access_token_ttl_seconds
    )
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def create_refresh_token() -> tuple[str, str]:
    """Return (raw_token, token_hash). Store the hash; send raw in the cookie."""
    raw = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, token_hash


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=settings.session_ttl_seconds)


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    _set_cookie(
        response, "access_token", access_token, settings.access_token_ttl_seconds
    )
    _set_cookie(
        response, "refresh_token", refresh_token, settings.session_ttl_seconds
    )


def clear_auth_cookies(response: Response) -> None:
    for name in ("access_token", "refresh_token"):
        response.delete_cookie(
            key=name,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
            domain=settings.cookie_domain or None,
        )


def _set_cookie(response: Response, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        key=name,
        value=value,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        domain=settings.cookie_domain or None,
        max_age=max_age,
    )
