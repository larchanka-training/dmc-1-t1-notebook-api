from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

# Runtime-only fields that are never persisted.
_RUNTIME_KEYS = {"executionCount", "output", "executionState"}


def strip_runtime(cell: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in cell.items() if k not in _RUNTIME_KEYS}


def enrich_cell(cell: dict[str, Any]) -> dict[str, Any]:
    """Re-attach ephemeral defaults to code cells before serving."""
    if cell.get("type") == "code":
        return {
            **cell,
            "executionCount": None,
            "output": {"type": "execute_result", "text": ""},
            "executionState": "idle",
        }
    return cell


# ---- Request schemas ----

class NotebookCreate(BaseModel):
    title: str = "Untitled Notebook"


class NotebookMetadataUpdate(BaseModel):
    title: str


class NotebookUpdate(BaseModel):
    metadata: NotebookMetadataUpdate
    cells: list[dict[str, Any]]


# ---- Response schemas ----

class NotebookMetadataResponse(BaseModel):
    title: str


class NotebookResponse(BaseModel):
    id: UUID
    metadata: NotebookMetadataResponse
    cells: list[dict[str, Any]]
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}


class NotebookShellCell(BaseModel):
    id: str
    type: Literal["markdown", "code"]
    title: str
    preview: str


class NotebookShellResponse(BaseModel):
    id: UUID
    title: str
    language: Literal["JavaScript"] = "JavaScript"
    kernelStatus: Literal["idle"] = "idle"
    cells: list[NotebookShellCell]
