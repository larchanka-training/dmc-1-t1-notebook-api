import logging

from fastapi import APIRouter

from app.ai.context import build_context
from app.ai.validation import validate_ai_output
from app.schemas.ai import (
    ContextRequest,
    ContextResponse,
    ValidateRequest,
    ValidateResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/context", response_model=ContextResponse)
def build_notebook_context(body: ContextRequest) -> ContextResponse:
    """Собрать контекст notebook для передачи в LLM (issue #124).

    Включает предыдущие ячейки (markdown, код и их outputs) до Prompt Cell.
    Результат (`prompt`) подставляется в промпт перед генерацией кода —
    вход в пайплайн валидации/repair из issue #125.
    """
    ctx = build_context(
        body.cells,
        target_cell_id=body.targetCellId,
        include_outputs=body.includeOutputs,
    )
    logger.info(
        "AI context: total=%d included=%d truncated=%s target=%s",
        ctx.total_cells,
        ctx.included_cells,
        ctx.truncated,
        body.targetCellId,
    )
    return ContextResponse.from_context(ctx)


@router.post("/validate", response_model=ValidateResponse)
def validate_ai_response(body: ValidateRequest) -> ValidateResponse:
    """Валидация ответа ИИ перед выводом в Code Cell.

    Извлекает код из произвольного ответа LLM (markdown-ограждения, текст с
    пояснениями, без ограждений) и проверяет синтаксис JS. Возвращает
    извлечённый код и диагностику; вызывающая сторона решает, показывать ли
    результат или запросить перегенерацию (см. пайплайн issue #125).
    """
    result = validate_ai_output(body.raw)
    logger.info(
        "AI validate: reason=%s valid=%s validator=%s raw_len=%d issues=%d",
        result.reason,
        result.is_valid,
        result.validator,
        len(body.raw or ""),
        len(result.issues),
    )
    return ValidateResponse.from_result(result)
