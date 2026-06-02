import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_user
from app.db.models.notebook import Notebook
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.notebook import (
    NotebookCreate,
    NotebookMetadataResponse,
    NotebookResponse,
    NotebookShellCell,
    NotebookShellResponse,
    NotebookUpdate,
    enrich_cell,
    strip_runtime,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notebooks", tags=["notebooks"])


def _to_response(notebook: Notebook) -> NotebookResponse:
    return NotebookResponse(
        id=notebook.id,
        metadata=NotebookMetadataResponse(title=notebook.title),
        cells=[enrich_cell(c) for c in notebook.cells],
        createdAt=notebook.created_at,
        updatedAt=notebook.updated_at,
    )


def _to_shell(notebook: Notebook) -> NotebookShellResponse:
    shell_cells: list[NotebookShellCell] = []
    for cell in notebook.cells:
        cell_type = cell.get("type")
        if cell_type == "raw":
            continue
        source: str = cell.get("source", "")
        first_line = source.split("\n")[0]
        title = first_line.lstrip("#").strip()[:60] or cell["id"]
        shell_cells.append(
            NotebookShellCell(
                id=cell["id"],
                type=cell_type,
                title=title,
                preview=source[:120],
            )
        )
    return NotebookShellResponse(
        id=notebook.id,
        title=notebook.title,
        cells=shell_cells,
    )


async def _get_owned(
    notebook_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Notebook:
    result = await db.execute(
        select(Notebook).where(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    notebook = result.scalar_one_or_none()
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return notebook


@router.get("", response_model=list[NotebookShellResponse])
async def list_notebooks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[NotebookShellResponse]:
    result = await db.execute(
        select(Notebook)
        .where(Notebook.user_id == current_user.id)
        .order_by(Notebook.updated_at.desc())
    )
    notebooks = result.scalars().all()
    return [_to_shell(n) for n in notebooks]


@router.post("", response_model=NotebookResponse, status_code=201)
async def create_notebook(
    body: NotebookCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotebookResponse:
    initial_cell = {
        "id": str(uuid.uuid4()),
        "type": "code",
        "source": "",
    }
    notebook = Notebook(
        user_id=current_user.id,
        title=body.title,
        cells=[initial_cell],
    )
    db.add(notebook)
    await db.commit()
    await db.refresh(notebook)
    logger.info("Notebook created: %s by user %s", notebook.id, current_user.id)
    return _to_response(notebook)


@router.get("/{notebook_id}", response_model=NotebookResponse)
async def get_notebook(
    notebook_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotebookResponse:
    notebook = await _get_owned(notebook_id, current_user, db)
    return _to_response(notebook)


@router.get("/{notebook_id}/shell", response_model=NotebookShellResponse)
async def get_notebook_shell(
    notebook_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotebookShellResponse:
    notebook = await _get_owned(notebook_id, current_user, db)
    return _to_shell(notebook)


@router.put("/{notebook_id}", response_model=NotebookResponse)
async def save_notebook(
    notebook_id: uuid.UUID,
    body: NotebookUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotebookResponse:
    notebook = await _get_owned(notebook_id, current_user, db)
    notebook.title = body.metadata.title
    notebook.cells = [strip_runtime(c) for c in body.cells]
    notebook.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(notebook)
    return _to_response(notebook)


@router.delete("/{notebook_id}", status_code=204)
async def delete_notebook(
    notebook_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    notebook = await _get_owned(notebook_id, current_user, db)
    await db.delete(notebook)
    await db.commit()
    logger.info("Notebook deleted: %s by user %s", notebook_id, current_user.id)
