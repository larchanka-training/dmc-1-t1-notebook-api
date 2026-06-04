"""Валидация и «починка» (repair) ответов LLM перед выводом в Code Cell.

Пайплайн (issue #125): Prompt Cell -> LLM -> Validator -> Code Cell.

Разные модели возвращают ответ по-разному: код в markdown-ограждении
(```js ... ```), без указания языка, вперемешку с пояснениями или вовсе без
ограждений. Этот модуль нормализует такие варианты, извлекает исполняемый JS
и проверяет его синтаксис. При ошибке синтаксиса поддерживается retry-цикл с
передачей информации об ошибке обратно в LLM (`generate_validated_code`).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from typing import Callable, Protocol, runtime_checkable

from app.ai.exceptions import AICodeNotFound, AIEmptyResponse, AIRepairFailed

logger = logging.getLogger(__name__)

# --- Нормализация языка fenced-блоков ----------------------------------------

_LANG_ALIASES = {
    "js": "javascript",
    "javascript": "javascript",
    "node": "javascript",
    "nodejs": "javascript",
    "jsx": "javascript",
    "mjs": "javascript",
    "cjs": "javascript",
    "ts": "typescript",
    "typescript": "typescript",
    "tsx": "typescript",
}
_JS_FAMILY = {"javascript", "typescript"}

_FENCE_OPEN_RE = re.compile(r"```([^\n`]*)\n")


def _normalize_lang(label: str) -> str:
    token = label.strip().split()[0].lower() if label.strip() else ""
    return _LANG_ALIASES.get(token, "")


def _extract_blocks(text: str) -> list[tuple[str, str]]:
    """Найти fenced-блоки. Толерантно к незакрытому последнему ограждению."""
    blocks: list[tuple[str, str]] = []
    pos = 0
    while True:
        match = _FENCE_OPEN_RE.search(text, pos)
        if not match:
            break
        lang = _normalize_lang(match.group(1))
        start = match.end()
        close = text.find("```", start)
        if close == -1:
            blocks.append((lang, text[start:]))
            break
        blocks.append((lang, text[start:close]))
        pos = close + 3
    return blocks


def extract_code(raw: str) -> tuple[str, str]:
    """Извлечь исполняемый код и язык из произвольного ответа LLM.

    Raises:
        AIEmptyResponse: пустой ответ.
        AICodeNotFound: код не найден.
    """
    if raw is None or not raw.strip():
        raise AIEmptyResponse("AI response is empty")

    text = raw.strip()
    blocks = [(lang, content.strip()) for lang, content in _extract_blocks(text)]
    blocks = [(lang, content) for lang, content in blocks if content]

    if blocks:
        js_blocks = [content for lang, content in blocks if lang in _JS_FAMILY]
        chosen = js_blocks if js_blocks else [content for _, content in blocks]
        labels = {lang for lang, _ in blocks if lang}
        if "javascript" in labels:
            language = "javascript"
        elif "typescript" in labels:
            language = "typescript"
        else:
            language = "javascript"
        return "\n\n".join(chosen), language

    if "```" in text:
        raise AICodeNotFound("fenced code block is empty")

    code = text
    if len(code) >= 2 and code.startswith("`") and code.endswith("`"):
        code = code.strip("`").strip()
    if not code:
        raise AICodeNotFound("no code found in AI response")
    return code, "javascript"


# --- Структуры результата ----------------------------------------------------

@dataclass(frozen=True)
class SyntaxIssue:
    message: str
    line: int | None = None
    column: int | None = None

    def __str__(self) -> str:
        if self.line is not None:
            loc = f"line {self.line}"
            if self.column is not None:
                loc += f", column {self.column}"
            return f"{loc}: {self.message}"
        return self.message


@dataclass(frozen=True)
class ValidationResult:
    raw: str
    code: str
    is_valid: bool
    language: str
    reason: str  # "ok" | "empty" | "no_code" | "syntax"
    issues: tuple[SyntaxIssue, ...] = ()
    validator: str = ""
    attempt: int = 1

    def error_summary(self) -> str:
        """Текст для передачи обратно в LLM при retry."""
        if self.is_valid:
            return ""
        if self.reason == "empty":
            return "The AI returned an empty response; no code was produced."
        if self.reason == "no_code":
            return (
                "No JavaScript code block was found in the response. "
                "Reply with the code inside a ```js code block."
            )
        if self.reason == "syntax":
            lines = "\n".join(f"- {issue}" for issue in self.issues)
            return f"The generated JavaScript has syntax errors:\n{lines}"
        return "The generated output is not valid."


# --- Проверка синтаксиса -----------------------------------------------------

@runtime_checkable
class SyntaxValidator(Protocol):
    """Контракт проверки синтаксиса. Пустой список == код валиден."""

    name: str

    def validate(self, code: str) -> list[SyntaxIssue]:
        ...


def _esprima_error_to_issue(exc: Exception) -> SyntaxIssue:
    message = (
        getattr(exc, "description", None)
        or getattr(exc, "message", None)
        or str(exc)
    )
    return SyntaxIssue(
        message=str(message),
        line=getattr(exc, "lineNumber", None),
        column=getattr(exc, "column", None),
    )


class EsprimaSyntaxValidator:
    """Точная проверка через парсер esprima (чистый Python, ES2017).

    Ограничение: часть синтаксиса ES2020+ (optional chaining ``?.``,
    nullish coalescing ``??``) может отклоняться. См. структурный fallback.
    """

    name = "esprima"

    def __init__(self) -> None:
        import esprima  # noqa: F401  -- ImportError -> fallback на структурный

        self._esprima = esprima

    def validate(self, code: str) -> list[SyntaxIssue]:
        if not code.strip():
            return [SyntaxIssue("code is empty")]
        script_error = self._try_parse(self._esprima.parseScript, code)
        if script_error is None:
            return []
        # Скрипт не распарсился — пробуем как ES-модуль (import/export).
        if self._try_parse(self._esprima.parseModule, code) is None:
            return []
        return [script_error]

    def _try_parse(self, parse_fn: Callable[[str], object], code: str):
        try:
            parse_fn(code)
        except Exception as exc:  # esprima бросает собственный Error
            return _esprima_error_to_issue(exc)
        return None


_OPEN_TO_CLOSE = {"(": ")", "[": "]", "{": "}"}
_CLOSE_TO_OPEN = {")": "(", "]": "[", "}": "{"}


def _scan_string(code: str, i: int, quote: str, line: int, col: int):
    """Пройти строковый литерал. Возврат (i, line, col) или SyntaxIssue."""
    n = len(code)
    i += 1
    col += 1
    while i < n:
        ch = code[i]
        if ch == "\\":
            if i + 1 < n and code[i + 1] == "\n":
                line += 1
                col = 1
                i += 2
            else:
                i += 2
                col += 2
            continue
        if ch == quote:
            return i + 1, line, col + 1
        if ch == "\n":
            return SyntaxIssue("unterminated string literal", line, col)
        i += 1
        col += 1
    return SyntaxIssue("unterminated string literal", line, col)


def _structural_issues(code: str) -> list[SyntaxIssue]:
    """Лёгкая проверка: баланс скобок/кавычек/шаблонов и комментарии.

    Не полноценный парсер: regex-литералы не распознаются (известное
    ограничение fallback'а). Используется только при отсутствии esprima.
    """
    if not code.strip():
        return [SyntaxIssue("code is empty")]

    stack: list[tuple[str, int, int]] = []
    n = len(code)
    i = 0
    line = 1
    col = 1

    while i < n:
        top = stack[-1][0] if stack else None

        # Внутри шаблонного литерала — посимвольное сканирование.
        if top == "`":
            ch = code[i]
            if ch == "\\":
                if i + 1 < n and code[i + 1] == "\n":
                    line += 1
                    col = 1
                    i += 2
                else:
                    i += 2
                    col += 2
                continue
            if ch == "`":
                stack.pop()
                i += 1
                col += 1
                continue
            if ch == "$" and i + 1 < n and code[i + 1] == "{":
                stack.append(("{", line, col))
                i += 2
                col += 2
                continue
            if ch == "\n":
                line += 1
                col = 1
                i += 1
                continue
            i += 1
            col += 1
            continue

        ch = code[i]
        nxt = code[i + 1] if i + 1 < n else ""

        if ch == "\n":
            line += 1
            col = 1
            i += 1
            continue
        if ch == "/" and nxt == "/":
            while i < n and code[i] != "\n":
                i += 1
            continue
        if ch == "/" and nxt == "*":
            end = code.find("*/", i + 2)
            if end == -1:
                return [SyntaxIssue("unterminated block comment", line, col)]
            segment = code[i:end + 2]
            line += segment.count("\n")
            last_nl = segment.rfind("\n")
            col = len(segment) - last_nl if last_nl != -1 else col + len(segment)
            i = end + 2
            continue
        if ch in ("'", '"'):
            res = _scan_string(code, i, ch, line, col)
            if isinstance(res, SyntaxIssue):
                return [res]
            i, line, col = res
            continue
        if ch in _OPEN_TO_CLOSE or ch == "`":
            stack.append((ch, line, col))
            i += 1
            col += 1
            continue
        if ch in _CLOSE_TO_OPEN:
            if not stack or stack[-1][0] != _CLOSE_TO_OPEN[ch]:
                return [SyntaxIssue(f"unexpected closing '{ch}'", line, col)]
            stack.pop()
            i += 1
            col += 1
            continue
        i += 1
        col += 1

    if stack:
        opener, oline, ocol = stack[-1]
        if opener == "`":
            return [SyntaxIssue("unterminated template literal", oline, ocol)]
        return [SyntaxIssue(f"unclosed '{opener}'", oline, ocol)]
    return []


class StructuralSyntaxValidator:
    """Структурный fallback без внешних зависимостей."""

    name = "structural"

    def validate(self, code: str) -> list[SyntaxIssue]:
        return _structural_issues(code)


_default_validator: SyntaxValidator | None = None


def get_default_validator() -> SyntaxValidator:
    """esprima по умолчанию, структурный fallback при отсутствии esprima."""
    global _default_validator
    if _default_validator is None:
        try:
            _default_validator = EsprimaSyntaxValidator()
        except ImportError:
            logger.warning("esprima unavailable; using structural syntax fallback")
            _default_validator = StructuralSyntaxValidator()
    return _default_validator


# --- Публичный API: валидация и repair-пайплайн ------------------------------

def validate_ai_output(
    raw: str,
    *,
    validator: SyntaxValidator | None = None,
) -> ValidationResult:
    """Извлечь код из ответа LLM и проверить синтаксис.

    Не бросает исключения для «нормальных» проблем (пустой ответ, нет кода,
    синтаксис) — они отражаются в ``ValidationResult.reason``/``issues``.
    """
    validator = validator or get_default_validator()
    try:
        code, language = extract_code(raw)
    except AIEmptyResponse as exc:
        return ValidationResult(
            raw=raw or "",
            code="",
            is_valid=False,
            language="",
            reason="empty",
            issues=(SyntaxIssue(str(exc)),),
            validator=validator.name,
        )
    except AICodeNotFound as exc:
        return ValidationResult(
            raw=raw,
            code="",
            is_valid=False,
            language="",
            reason="no_code",
            issues=(SyntaxIssue(str(exc)),),
            validator=validator.name,
        )

    issues = tuple(validator.validate(code))
    return ValidationResult(
        raw=raw,
        code=code,
        is_valid=not issues,
        language=language,
        reason="ok" if not issues else "syntax",
        issues=issues,
        validator=validator.name,
    )


RegenerateFn = Callable[[str, "ValidationResult | None"], str]


def generate_validated_code(
    prompt: str,
    regenerate: RegenerateFn,
    *,
    max_attempts: int = 3,
    validator: SyntaxValidator | None = None,
) -> ValidationResult:
    """Пайплайн Prompt -> LLM -> Validator с retry-циклом.

    ``regenerate(prompt, last_result)`` вызывает LLM: ``last_result`` равен
    ``None`` на первой попытке, иначе содержит предыдущий неуспешный результат
    (используйте ``last_result.error_summary()`` для уточняющего промпта).

    Raises:
        AIRepairFailed: валидный код не получен за ``max_attempts`` попыток.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    validator = validator or get_default_validator()

    last: ValidationResult | None = None
    for attempt in range(1, max_attempts + 1):
        raw = regenerate(prompt, last)
        result = replace(
            validate_ai_output(raw, validator=validator), attempt=attempt
        )
        if result.is_valid:
            logger.info(
                "AI code validated on attempt %d/%d", attempt, max_attempts
            )
            return result
        logger.warning(
            "AI code invalid on attempt %d/%d: reason=%s",
            attempt,
            max_attempts,
            result.reason,
        )
        last = result

    raise AIRepairFailed(
        f"failed to obtain valid code after {max_attempts} attempt(s)",
        attempts=max_attempts,
        last_result=last,
    )
