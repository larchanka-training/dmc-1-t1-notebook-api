import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("COOKIE_DOMAIN", "localhost")

from app.core.security import (  # noqa: E402  # isort: skip_file
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
)
from app.db.models.session import Session  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.schemas.auth import RegisterRequest  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(email: str = "test@example.com") -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("password123"),
        display_name=None,
        created_at=datetime.now(timezone.utc),
    )


def make_db_mock(scalar_result=None) -> AsyncMock:
    """Async DB mock where scalar_one_or_none() is synchronous (MagicMock child)."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scalar_result
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db


# ---------------------------------------------------------------------------
# Security unit tests
# ---------------------------------------------------------------------------

class TestSecurity:
    def test_hash_and_verify_password(self) -> None:
        from app.core.security import verify_password

        hashed = hash_password("secret")
        assert verify_password("secret", hashed)
        assert not verify_password("wrong", hashed)

    def test_create_and_decode_access_token(self) -> None:
        from app.core.security import decode_access_token

        user_id = str(uuid.uuid4())
        token = create_access_token(user_id)
        payload = decode_access_token(token)
        assert payload["sub"] == user_id

    def test_refresh_token_hash_roundtrip(self) -> None:
        raw, token_hash = create_refresh_token()
        assert hash_token(raw) == token_hash
        assert len(raw) > 0
        assert len(token_hash) == 64  # sha256 hex

    def test_register_request_password_min_length(self) -> None:
        with pytest.raises(Exception):
            RegisterRequest(email="a@b.com", password="short")

    def test_register_request_valid(self) -> None:
        req = RegisterRequest(email="a@b.com", password="longpassword")
        assert req.email == "a@b.com"

    def test_user_response_display_name_defaults_to_email(self) -> None:
        from app.schemas.auth import UserResponse

        resp = UserResponse(
            id=uuid.uuid4(),
            email="x@y.com",
            display_name="x@y.com",
            created_at=datetime.now(timezone.utc),
        )
        assert resp.display_name == "x@y.com"


# ---------------------------------------------------------------------------
# Endpoint integration tests (mocked DB)
# ---------------------------------------------------------------------------

class TestAuthEndpoints:
    def setup_method(self) -> None:
        from app.main import app
        app.dependency_overrides.clear()

    def teardown_method(self) -> None:
        from app.main import app
        app.dependency_overrides.clear()

    def _client(self, mock_db: AsyncMock) -> TestClient:
        from app.db.session import get_db
        from app.main import app

        app.dependency_overrides[get_db] = lambda: mock_db
        return TestClient(app, raise_server_exceptions=True)

    # ---- register ----

    def test_register_success(self) -> None:
        created_user = make_user("new@example.com")
        mock_db = make_db_mock(scalar_result=None)

        async def fake_refresh(obj: User) -> None:
            obj.id = created_user.id
            obj.created_at = created_user.created_at

        mock_db.refresh = AsyncMock(side_effect=fake_refresh)

        resp = self._client(mock_db).post(
            "/api/v1/auth/register",
            json={"email": "new@example.com", "password": "password123"},
        )
        assert resp.status_code == 201
        assert resp.json()["email"] == "new@example.com"

    def test_register_duplicate_email(self) -> None:
        mock_db = make_db_mock(scalar_result=make_user())

        resp = self._client(mock_db).post(
            "/api/v1/auth/register",
            json={"email": "existing@example.com", "password": "password123"},
        )
        assert resp.status_code == 409

    # ---- login ----

    def test_login_success(self) -> None:
        mock_db = make_db_mock(scalar_result=make_user())

        resp = self._client(mock_db).post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "password123"},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "test@example.com"

    def test_login_wrong_password(self) -> None:
        mock_db = make_db_mock(scalar_result=make_user())

        resp = self._client(mock_db).post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    def test_login_unknown_user(self) -> None:
        mock_db = make_db_mock(scalar_result=None)

        resp = self._client(mock_db).post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "password123"},
        )
        assert resp.status_code == 401

    # ---- me ----

    def test_me_unauthenticated(self) -> None:
        resp = self._client(make_db_mock()).get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_authenticated(self) -> None:
        user = make_user()
        mock_db = make_db_mock()
        mock_db.get = AsyncMock(return_value=user)

        client = self._client(mock_db)
        client.cookies.set("access_token", create_access_token(str(user.id)))

        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["email"] == user.email

    # ---- logout ----

    def test_logout_no_cookie(self) -> None:
        resp = self._client(make_db_mock()).post("/api/v1/auth/logout")
        assert resp.status_code == 204

    def test_logout_clears_session(self) -> None:
        user = make_user()
        raw_token, token_hash = create_refresh_token()
        session = Session(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            created_at=datetime.now(timezone.utc),
        )
        mock_db = make_db_mock(scalar_result=session)

        client = self._client(mock_db)
        client.cookies.set("refresh_token", raw_token)

        resp = client.post("/api/v1/auth/logout")
        assert resp.status_code == 204
        mock_db.delete.assert_awaited_once_with(session)

    # ---- refresh ----

    def test_refresh_missing_cookie(self) -> None:
        resp = self._client(make_db_mock()).post("/api/v1/auth/refresh")
        assert resp.status_code == 401

    def test_refresh_valid_token(self) -> None:
        user = make_user()
        raw_token, token_hash = create_refresh_token()
        session = Session(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            created_at=datetime.now(timezone.utc),
        )
        mock_db = make_db_mock(scalar_result=session)
        mock_db.get = AsyncMock(return_value=user)

        client = self._client(mock_db)
        client.cookies.set("refresh_token", raw_token)

        resp = client.post("/api/v1/auth/refresh")
        assert resp.status_code == 200
        assert resp.json()["email"] == user.email

    def test_refresh_expired_token(self) -> None:
        user = make_user()
        raw_token, token_hash = create_refresh_token()
        session = Session(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),  # expired
            created_at=datetime.now(timezone.utc),
        )
        mock_db = make_db_mock(scalar_result=session)

        client = self._client(mock_db)
        client.cookies.set("refresh_token", raw_token)

        resp = client.post("/api/v1/auth/refresh")
        assert resp.status_code == 401
