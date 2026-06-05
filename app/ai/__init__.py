"""AI output validation & repair (issue #125).

Публичный API:
    - ``build_context`` — собрать контекст из предыдущих ячеек notebook (#124).
    - ``NotebookContext`` / ``ContextCell`` — структуры контекста.
    - ``validate_ai_output`` — извлечь код из ответа LLM и проверить синтаксис.
    - ``generate_validated_code`` — пайплайн с retry-циклом (repair).
    - ``ValidationResult`` / ``SyntaxIssue`` — структуры результата.
    - исключения AI-слоя (``app.ai.exceptions``).
"""

from app.ai.context import (
    ContextCell,
    NotebookContext,
    build_context,
    render_output,
)
from app.ai.exceptions import (
    AICodeNotFound,
    AIEmptyResponse,
    AIError,
    AIRepairFailed,
    AISyntaxError,
)
from app.ai.validation import (
    EsprimaSyntaxValidator,
    StructuralSyntaxValidator,
    SyntaxIssue,
    SyntaxValidator,
    ValidationResult,
    extract_code,
    generate_validated_code,
    get_default_validator,
    validate_ai_output,
)

__all__ = [
    "ContextCell",
    "NotebookContext",
    "build_context",
    "render_output",
    "AIError",
    "AIEmptyResponse",
    "AICodeNotFound",
    "AISyntaxError",
    "AIRepairFailed",
    "SyntaxIssue",
    "SyntaxValidator",
    "ValidationResult",
    "EsprimaSyntaxValidator",
    "StructuralSyntaxValidator",
    "extract_code",
    "validate_ai_output",
    "generate_validated_code",
    "get_default_validator",
]
