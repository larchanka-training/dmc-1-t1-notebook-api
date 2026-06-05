from typing import Any, Literal

from pydantic import BaseModel, Field

from app.ai.context import NotebookContext
from app.ai.validation import ValidationResult


class ContextRequest(BaseModel):
    """Запрос на сборку контекста notebook для передачи в LLM."""

    cells: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Ячейки notebook (id, type, source и output у code-ячеек).",
    )
    targetCellId: str | None = Field(
        default=None,
        description="id Prompt Cell; включаются только ячейки до неё.",
    )
    includeOutputs: bool = Field(
        default=True, description="Включать результаты выполнения code-ячеек."
    )


class ContextCellModel(BaseModel):
    index: int
    id: str
    type: str
    source: str
    output: str
    sourceTruncated: bool
    outputTruncated: bool


class ContextResponse(BaseModel):
    prompt: str
    cells: list[ContextCellModel]
    totalCells: int
    includedCells: int
    truncated: bool

    @classmethod
    def from_context(cls, ctx: NotebookContext) -> "ContextResponse":
        return cls(
            prompt=ctx.to_prompt(),
            cells=[
                ContextCellModel(
                    index=c.index,
                    id=c.id,
                    type=c.type,
                    source=c.source,
                    output=c.output,
                    sourceTruncated=c.source_truncated,
                    outputTruncated=c.output_truncated,
                )
                for c in ctx.cells
            ],
            totalCells=ctx.total_cells,
            includedCells=ctx.included_cells,
            truncated=ctx.truncated,
        )


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
