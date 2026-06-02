import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("COOKIE_DOMAIN", "localhost")

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.models.notebook import Notebook  # noqa: E402
from app.db.models.user import User  # noqa: E402


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


def make_notebook(user_id: uuid.UUID, title: str = "My Notebook") -> Notebook:
    now = datetime.now(timezone.utc)
    nb = Notebook(
        id=uuid.uuid4(),
        user_id=user_id,
        title=title,
        cells=[
            {"id": str(uuid.uuid4()), "type": "code", "source": "console.log('hi')"},
            {"id": str(uuid.uuid4()), "type": "markdown", "source": "# Hello"},
        ],
        created_at=now,
        updated_at=now,
    )
    return nb


def make_scalars_mock(items: list) -> MagicMock:
    scalars = MagicMock()
    scalars.all.return_value = items
    result = MagicMock()
    result.scalars.return_value = scalars
    result.scalar_one_or_none.return_value = items[0] if items else None
    return result


def make_db_mock(execute_result=None) -> AsyncMock:
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=execute_result or MagicMock())
    return mock_db


# ---------------------------------------------------------------------------
# Schema unit tests
# ---------------------------------------------------------------------------

class TestSchemas:
    def test_strip_runtime_removes_execution_fields(self) -> None:
        from app.schemas.notebook import strip_runtime

        cell = {
            "id": "c1",
            "type": "code",
            "source": "x = 1",
            "executionCount": 3,
            "output": {"type": "execute_result", "text": "3"},
            "executionState": "idle",
        }
        stripped = strip_runtime(cell)
        assert "executionCount" not in stripped
        assert "output" not in stripped
        assert "executionState" not in stripped
        assert stripped["source"] == "x = 1"

    def test_strip_runtime_leaves_non_code_cells_intact(self) -> None:
        from app.schemas.notebook import strip_runtime

        cell = {"id": "c2", "type": "markdown", "source": "# Hi"}
        assert strip_runtime(cell) == cell

    def test_enrich_cell_adds_defaults_to_code_cell(self) -> None:
        from app.schemas.notebook import enrich_cell

        cell = {"id": "c1", "type": "code", "source": "x = 1"}
        enriched = enrich_cell(cell)
        assert enriched["executionCount"] is None
        assert enriched["executionState"] == "idle"
        assert enriched["output"] == {"type": "execute_result", "text": ""}

    def test_enrich_cell_leaves_markdown_unchanged(self) -> None:
        from app.schemas.notebook import enrich_cell

        cell = {"id": "c2", "type": "markdown", "source": "# Hi"}
        assert enrich_cell(cell) == cell


# ---------------------------------------------------------------------------
# Endpoint tests (mocked DB)
# ---------------------------------------------------------------------------

class TestNotebookEndpoints:
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

    # ---- list ----

    def test_list_notebooks_returns_shells(self) -> None:
        user = make_user()
        nb = make_notebook(user.id)
        mock_db = make_db_mock(execute_result=make_scalars_mock([nb]))

        resp = self._client(mock_db, user).get("/api/v1/notebooks")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == nb.title
        assert data[0]["language"] == "JavaScript"
        assert data[0]["kernelStatus"] == "idle"
        assert len(data[0]["cells"]) == 2  # raw cells filtered out, both code+md included

    def test_list_notebooks_unauthenticated(self) -> None:
        mock_db = make_db_mock()
        resp = self._unauth_client(mock_db).get("/api/v1/notebooks")
        assert resp.status_code == 401

    def test_list_notebooks_empty(self) -> None:
        user = make_user()
        mock_db = make_db_mock(execute_result=make_scalars_mock([]))

        resp = self._client(mock_db, user).get("/api/v1/notebooks")
        assert resp.status_code == 200
        assert resp.json() == []

    # ---- create ----

    def test_create_notebook_success(self) -> None:
        user = make_user()
        created_nb = make_notebook(user.id, title="New NB")
        mock_db = make_db_mock()

        async def fake_refresh(obj: Notebook) -> None:
            obj.id = created_nb.id
            obj.created_at = created_nb.created_at
            obj.updated_at = created_nb.updated_at

        mock_db.refresh = AsyncMock(side_effect=fake_refresh)

        resp = self._client(mock_db, user).post(
            "/api/v1/notebooks", json={"title": "New NB"}
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["metadata"]["title"] == "New NB"
        assert len(data["cells"]) == 1
        assert data["cells"][0]["type"] == "code"
        assert data["cells"][0]["executionCount"] is None
        assert data["cells"][0]["executionState"] == "idle"

    def test_create_notebook_unauthenticated(self) -> None:
        mock_db = make_db_mock()
        resp = self._unauth_client(mock_db).post(
            "/api/v1/notebooks", json={"title": "NB"}
        )
        assert resp.status_code == 401

    # ---- get by id ----

    def test_get_notebook_success(self) -> None:
        user = make_user()
        nb = make_notebook(user.id)
        mock_db = make_db_mock(execute_result=make_scalars_mock([nb]))

        resp = self._client(mock_db, user).get(f"/api/v1/notebooks/{nb.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["metadata"]["title"] == nb.title
        # Code cells get runtime defaults
        code_cell = next(c for c in data["cells"] if c["type"] == "code")
        assert code_cell["executionCount"] is None
        assert code_cell["executionState"] == "idle"

    def test_get_notebook_not_found(self) -> None:
        user = make_user()
        mock_db = make_db_mock(execute_result=make_scalars_mock([]))

        resp = self._client(mock_db, user).get(f"/api/v1/notebooks/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_get_notebook_unauthenticated(self) -> None:
        mock_db = make_db_mock()
        resp = self._unauth_client(mock_db).get(f"/api/v1/notebooks/{uuid.uuid4()}")
        assert resp.status_code == 401

    # ---- shell ----

    def test_get_notebook_shell_success(self) -> None:
        user = make_user()
        nb = make_notebook(user.id)
        mock_db = make_db_mock(execute_result=make_scalars_mock([nb]))

        resp = self._client(mock_db, user).get(f"/api/v1/notebooks/{nb.id}/shell")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == nb.title
        assert data["language"] == "JavaScript"
        assert all("preview" in c for c in data["cells"])

    # ---- save (PUT) ----

    def test_save_notebook_success(self) -> None:
        user = make_user()
        nb = make_notebook(user.id)
        mock_db = make_db_mock(execute_result=make_scalars_mock([nb]))

        async def fake_refresh(obj: Notebook) -> None:
            pass

        mock_db.refresh = AsyncMock(side_effect=fake_refresh)

        payload = {
            "metadata": {"title": "Updated Title"},
            "cells": [
                {
                    "id": "c1",
                    "type": "code",
                    "source": "x = 2",
                    "executionCount": 5,
                    "output": {"type": "execute_result", "text": "2"},
                    "executionState": "idle",
                }
            ],
        }
        resp = self._client(mock_db, user).put(
            f"/api/v1/notebooks/{nb.id}", json=payload
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["metadata"]["title"] == "Updated Title"
        # Runtime fields stripped on save, then re-added as defaults
        assert data["cells"][0]["executionCount"] is None
        assert data["cells"][0]["source"] == "x = 2"

    def test_save_notebook_not_found(self) -> None:
        user = make_user()
        mock_db = make_db_mock(execute_result=make_scalars_mock([]))

        payload = {"metadata": {"title": "X"}, "cells": []}
        resp = self._client(mock_db, user).put(
            f"/api/v1/notebooks/{uuid.uuid4()}", json=payload
        )
        assert resp.status_code == 404

    # ---- delete ----

    def test_delete_notebook_success(self) -> None:
        user = make_user()
        nb = make_notebook(user.id)
        mock_db = make_db_mock(execute_result=make_scalars_mock([nb]))

        resp = self._client(mock_db, user).delete(f"/api/v1/notebooks/{nb.id}")
        assert resp.status_code == 204
        mock_db.delete.assert_awaited_once_with(nb)

    def test_delete_notebook_not_found(self) -> None:
        user = make_user()
        mock_db = make_db_mock(execute_result=make_scalars_mock([]))

        resp = self._client(mock_db, user).delete(f"/api/v1/notebooks/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_delete_notebook_unauthenticated(self) -> None:
        mock_db = make_db_mock()
        resp = self._unauth_client(mock_db).delete(f"/api/v1/notebooks/{uuid.uuid4()}")
        assert resp.status_code == 401
