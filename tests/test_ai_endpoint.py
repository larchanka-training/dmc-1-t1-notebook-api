import os

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("COOKIE_DOMAIN", "localhost")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_validate_endpoint_ok() -> None:
    resp = client.post(
        "/api/v1/ai/validate",
        json={"raw": "Here:\n```js\nconst x = 1;\nconsole.log(x);\n```"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["isValid"] is True
    assert data["reason"] == "ok"
    assert data["code"] == "const x = 1;\nconsole.log(x);"
    assert data["language"] == "javascript"
    assert data["issues"] == []


def test_validate_endpoint_empty() -> None:
    resp = client.post("/api/v1/ai/validate", json={"raw": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert data["isValid"] is False
    assert data["reason"] == "empty"


def test_validate_endpoint_no_code() -> None:
    resp = client.post("/api/v1/ai/validate", json={"raw": "```js\n```"})
    assert resp.status_code == 200
    assert resp.json()["reason"] == "no_code"


def test_validate_endpoint_syntax_error() -> None:
    resp = client.post(
        "/api/v1/ai/validate",
        json={"raw": "```js\nconsole.log(\n```"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["isValid"] is False
    assert data["reason"] == "syntax"
    assert data["issues"]


def test_validate_endpoint_requires_raw_field() -> None:
    resp = client.post("/api/v1/ai/validate", json={})
    assert resp.status_code == 422
