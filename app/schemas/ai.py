from typing import Literal

from pydantic import BaseModel, Field

from app.ai.validation import ValidationResult


class ValidateRequest(BaseModel):
    """Запрос на валидацию сырого ответа LLM перед выводом в Code Cell."""

    raw: str = Field(
        ...,
        description="Сырой текст ответа LLM (может содержать markdown/пояснения).",
    )


class SyntaxIssueModel(BaseModel):
    message: str
    line: int | None = None
    column: int | None = None


class ValidateResponse(BaseModel):
    isValid: bool
    code: str
    language: str
    reason: Literal["ok", "empty", "no_code", "syntax"]
    issues: list[SyntaxIssueModel]
    validator: str

    @classmethod
    def from_result(cls, result: ValidationResult) -> "ValidateResponse":
        return cls(
            isValid=result.is_valid,
            code=result.code,
            language=result.language,
            reason=result.reason,
            issues=[
                SyntaxIssueModel(message=i.message, line=i.line, column=i.column)
                for i in result.issues
            ],
            validator=result.validator,
        )
