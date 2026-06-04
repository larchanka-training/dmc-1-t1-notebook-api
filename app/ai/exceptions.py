"""Иерархия исключений AI-слоя.

Все отклонения формата ответа LLM нормализуются в подклассы ``AIError``,
по аналогии с ``LLMBadResponse`` из референс-проекта ai-multi-agent-system.
"""

from __future__ import annotations


class AIError(Exception):
    """Базовое исключение AI-слоя."""


class AIEmptyResponse(AIError):
    """LLM вернула пустой ответ (нет содержимого для валидации)."""


class AICodeNotFound(AIError):
    """В ответе LLM не удалось найти исполняемый код."""


class AISyntaxError(AIError):
    """Извлечённый код не прошёл проверку синтаксиса."""

    def __init__(
        self,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        super().__init__(message)
        self.line = line
        self.column = column


class AIRepairFailed(AIError):
    """Repair-цикл исчерпал попытки, валидный код не получен."""

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        last_result: object | None = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.last_result = last_result
