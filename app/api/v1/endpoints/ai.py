import logging

from fastapi import APIRouter

from app.ai.validation import validate_ai_output
from app.schemas.ai import ValidateRequest, ValidateResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


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
