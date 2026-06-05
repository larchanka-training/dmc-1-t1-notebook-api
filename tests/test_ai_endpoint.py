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


def test_context_endpoint_builds_prompt() -> None:
    resp = client.post(
        "/api/v1/ai/context",
        json={
            "cells": [
                {"id": "m1", "type": "markdown", "source": "# Setup"},
                {
                    "id": "c1",
                    "type": "code",
                    "source": "const x = 1;",
                    "output": {"type": "execute_result", "text": "1"},
                },
                {"id": "prompt", "type": "code", "source": "// task"},
            ],
            "targetCellId": "prompt",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["totalCells"] == 3
    assert data["includedCells"] == 2
    assert data["truncated"] is False
    assert "# Setup" in data["prompt"]
    assert "const x = 1;" in data["prompt"]
    assert "Output:" in data["prompt"]
    assert [c["id"] for c in data["cells"]] == ["m1", "c1"]


def test_context_endpoint_empty_cells() -> None:
    resp = client.post("/api/v1/ai/context", json={"cells": []})
    assert resp.status_code == 200
    data = resp.json()
    assert data["includedCells"] == 0
    assert data["prompt"] == ""


def test_context_endpoint_exclude_outputs() -> None:
    resp = client.post(
        "/api/v1/ai/context",
        json={
            "cells": [
                {
                    "id": "c1",
                    "type": "code",
                    "source": "x",
                    "output": {"type": "execute_result", "text": "1"},
                }
            ],
            "includeOutputs": False,
        },
    )
    assert resp.status_code == 200
    assert "Output:" not in resp.json()["prompt"]
