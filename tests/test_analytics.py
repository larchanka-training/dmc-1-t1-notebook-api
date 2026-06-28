import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("COOKIE_DOMAIN", "localhost")

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.models.analytics import AnalyticsEvent  # noqa: E402
from app.db.models.user import User  # noqa: E402


def make_user(email: str = "analytics@example.com") -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("password123"),
        display_name=None,
        created_at=datetime.now(timezone.utc),
    )


def make_event(
    user_id: uuid.UUID,
    event_type: str = "notebook_created",
    metadata: dict | None = None,
) -> AnalyticsEvent:
    return AnalyticsEvent(
        id=uuid.uuid4(),
        user_id=user_id,
        event_type=event_type,
        event_metadata=metadata or {},
        created_at=datetime.now(timezone.utc),
    )


class TestAnalyticsEndpoints:
    def setup_method(self) -> None:
        from app.main import app
        app.dependency_overrides.clear()

    def teardown_method(self) -> None:
        from app.main import app
        app.dependency_overrides.clear()

    def _client(self, mock_db: AsyncMock, user: User) -> TestClient:
        from app.api.v1.endpoints.auth import get_current_user
        from app.db.session import get_db
        from app.main import app

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: user

        client = TestClient(app, raise_server_exceptions=True)
        client.cookies.set("access_token", create_access_token(str(user.id)))
        return client

    def _unauth_client(self, mock_db: AsyncMock) -> TestClient:
        from app.db.session import get_db
        from app.main import app

        app.dependency_overrides[get_db] = lambda: mock_db
        return TestClient(app, raise_server_exceptions=True)

    # ---- POST /analytics/events ----

    def test_create_event_success(self) -> None:
        user = make_user()
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        async def _refresh(obj):
            obj.id = uuid.uuid4()
            obj.created_at = datetime.now(timezone.utc)

        mock_db.refresh = AsyncMock(side_effect=_refresh)

        client = self._client(mock_db, user)
        resp = client.post(
            "/api/v1/analytics/events",
            json={"event_type": "notebook_created", "metadata": {"notebook_id": "abc"}},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["event_type"] == "notebook_created"
        assert data["metadata"] == {"notebook_id": "abc"}
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()

    def test_create_event_invalid_type(self) -> None:
        user = make_user()
        mock_db = AsyncMock()

        client = self._client(mock_db, user)
        resp = client.post(
            "/api/v1/analytics/events",
            json={"event_type": "invalid_type", "metadata": {}},
        )
        assert resp.status_code == 422

    def test_create_event_unauthorized(self) -> None:
        mock_db = AsyncMock()
        client = self._unauth_client(mock_db)
        resp = client.post(
            "/api/v1/analytics/events",
            json={"event_type": "notebook_created", "metadata": {}},
        )
        assert resp.status_code == 401

    # ---- GET /analytics/dashboard ----

    def test_dashboard_returns_counts(self) -> None:
        user = make_user()
        event1 = make_event(user.id, "notebook_created")
        event2 = make_event(user.id, "cell_executed")
        event3 = make_event(user.id, "cell_executed")

        # Mock: first call = group_by counts, second call = recent events
        count_result = MagicMock()
        count_result.all.return_value = [
            ("notebook_created", 1),
            ("cell_executed", 2),
        ]

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [event1, event2, event3]
        recent_result = MagicMock()
        recent_result.scalars.return_value = scalars_mock

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=[count_result, recent_result])

        client = self._client(mock_db, user)
        resp = client.get("/api/v1/analytics/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_events"] == 3
        by_type = {e["event_type"]: e["count"] for e in data["events_by_type"]}
        assert by_type["notebook_created"] == 1
        assert by_type["cell_executed"] == 2
        assert len(data["recent_events"]) == 3

    def test_dashboard_empty(self) -> None:
        user = make_user()

        count_result = MagicMock()
        count_result.all.return_value = []

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        recent_result = MagicMock()
        recent_result.scalars.return_value = scalars_mock

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=[count_result, recent_result])

        client = self._client(mock_db, user)
        resp = client.get("/api/v1/analytics/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_events"] == 0
        assert data["events_by_type"] == []
        assert data["recent_events"] == []

    def test_dashboard_unauthorized(self) -> None:
        mock_db = AsyncMock()
        client = self._unauth_client(mock_db)
        resp = client.get("/api/v1/analytics/dashboard")
        assert resp.status_code == 401
