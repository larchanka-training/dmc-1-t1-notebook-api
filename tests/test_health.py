import os
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("COOKIE_DOMAIN", "localhost")

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


def test_healthcheck() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "api_version" in data
    assert "environment" in data
    assert "service" in data


def test_healthcheck_returns_app_name() -> None:
    response = client.get("/api/v1/health")
    assert response.json()["service"] == settings.app_name


def test_health_db_not_configured() -> None:
    with patch.object(settings, "database_url", ""):
        response = client.get("/api/v1/health/db")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "not_configured"


def test_health_db_unavailable_returns_503() -> None:
    import psycopg2

    with patch.object(settings, "database_url", "postgresql://fake:fake@localhost/fake"):
        with patch.object(
            psycopg2, "connect", side_effect=Exception("connection refused")
        ):
            response = client.get("/api/v1/health/db")
    assert response.status_code == 503
    assert "Database unavailable" in response.json()["detail"]
