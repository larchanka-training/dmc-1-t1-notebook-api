import asyncio
import logging

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException

from app.ai.bedrock import invoke_model
from app.ai.context import build_context
from app.ai.exceptions import AIRepairFailed
from app.ai.prompt_guard import check_prompt
from app.ai.rate_limit import ai_rate_limiter
from app.core.config import settings
from app.ai.validation import ValidationResult, generate_validated_code, validate_ai_output
from app.api.v1.endpoints.auth import get_current_user
from app.db.models.user import User
from app.schemas.ai import (
    ContextRequest,
    ContextResponse,
    GenerateRequest,
    GenerateResponse,
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


@router.post("/generate", response_model=GenerateResponse)
async def generate_code(
    body: GenerateRequest,
    current_user: User = Depends(get_current_user),
) -> GenerateResponse:
    """Generate JavaScript code from a prompt using AWS Bedrock.

    Rate-limited per user (see AI_RATE_LIMIT_RPM / AI_RATE_LIMIT_RPD).
    Build the prompt with POST /ai/context before calling this endpoint.
    """
    if len(body.prompt) > settings.ai_max_prompt_chars:
        raise HTTPException(
            status_code=400,
            detail=f"Prompt too long (max {settings.ai_max_prompt_chars} characters)",
        )
    check_prompt(body.prompt)
    await ai_rate_limiter.enforce(str(current_user.id))

    def _regenerate(prompt: str, last: ValidationResult | None) -> str:
        full_prompt = prompt
        if last is not None:
            full_prompt = prompt + "\n\n" + last.error_summary()
        return invoke_model(full_prompt)

    try:
        result = await asyncio.to_thread(
            generate_validated_code,
            body.prompt,
            _regenerate,
            max_attempts=3,
        )
    except AIRepairFailed as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "ThrottlingException":
            raise HTTPException(status_code=429, detail="Bedrock throttled — retry shortly")
        raise HTTPException(status_code=503, detail=f"Bedrock error: {code}")

    logger.info(
        "AI generate: user=%s valid=%s attempts=%d",
        current_user.id,
        result.is_valid,
        result.attempt,
    )
    return GenerateResponse.from_result(result)


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
