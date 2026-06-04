import os

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("COOKIE_DOMAIN", "localhost")

from app.ai.exceptions import (  # noqa: E402
    AICodeNotFound,
    AIEmptyResponse,
    AIRepairFailed,
)
from app.ai.validation import (  # noqa: E402
    EsprimaSyntaxValidator,
    StructuralSyntaxValidator,
    extract_code,
    generate_validated_code,
    validate_ai_output,
)

STRUCTURAL = StructuralSyntaxValidator()

try:
    ESPRIMA = EsprimaSyntaxValidator()
except ImportError:  # pragma: no cover
    ESPRIMA = None

esprima_required = pytest.mark.skipif(ESPRIMA is None, reason="esprima not installed")


# ---------------------------------------------------------------------------
# extract_code — разные форматы ответов моделей
# ---------------------------------------------------------------------------

def test_extract_fenced_js_with_prose() -> None:
    raw = "Sure, here you go:\n```js\nconst x = 1;\n```\nHope it helps!"
    code, language = extract_code(raw)
    assert code == "const x = 1;"
    assert language == "javascript"


def test_extract_fence_without_language() -> None:
    raw = "```\nlet y = 2;\n```"
    code, language = extract_code(raw)
    assert code == "let y = 2;"
    assert language == "javascript"


def test_extract_bare_code_without_fence() -> None:
    code, language = extract_code("console.log(1)")
    assert code == "console.log(1)"
    assert language == "javascript"


def test_extract_multiple_js_blocks_are_joined() -> None:
    raw = "```js\na();\n```\nand then\n```javascript\nb();\n```"
    code, _ = extract_code(raw)
    assert code == "a();\n\nb();"


def test_extract_prefers_js_over_other_languages() -> None:
    raw = "Install first:\n```bash\nnpm i\n```\nthen run:\n```js\nrun();\n```"
    code, language = extract_code(raw)
    assert code == "run();"
    assert language == "javascript"


def test_extract_typescript_block_detected() -> None:
    raw = "```ts\nconst n: number = 1;\n```"
    code, language = extract_code(raw)
    assert code == "const n: number = 1;"
    assert language == "typescript"


def test_extract_unclosed_fence_takes_rest() -> None:
    code, _ = extract_code("```js\nconst x = 1;\nconsole.log(x)")
    assert code == "const x = 1;\nconsole.log(x)"


def test_extract_strips_inline_backticks() -> None:
    code, _ = extract_code("`const x = 1;`")
    assert code == "const x = 1;"


def test_extract_empty_raises() -> None:
    with pytest.raises(AIEmptyResponse):
        extract_code("")
    with pytest.raises(AIEmptyResponse):
        extract_code("   \n  ")


def test_extract_empty_fence_raises_code_not_found() -> None:
    with pytest.raises(AICodeNotFound):
        extract_code("```js\n```")


# ---------------------------------------------------------------------------
# Структурный валидатор (детерминированный, без зависимостей)
# ---------------------------------------------------------------------------

def test_structural_valid_code() -> None:
    assert STRUCTURAL.validate("const x = {a: [1, 2]};\nfoo(x);") == []


def test_structural_unbalanced_paren() -> None:
    issues = STRUCTURAL.validate("foo(")
    assert len(issues) == 1
    assert "unclosed '('" in issues[0].message


def test_structural_unexpected_closing() -> None:
    issues = STRUCTURAL.validate("foo)")
    assert "unexpected closing ')'" in issues[0].message


def test_structural_unterminated_string() -> None:
    issues = STRUCTURAL.validate('const s = "oops;')
    assert "unterminated string" in issues[0].message


def test_structural_ignores_brackets_in_strings_and_comments() -> None:
    code = 'const s = "(not code]";\n// ) ] }\n/* { ( */\nfoo();'
    assert STRUCTURAL.validate(code) == []


def test_structural_template_literal_with_interpolation() -> None:
    assert STRUCTURAL.validate("const s = `a ${ obj.b } c`;") == []


def test_structural_unterminated_template() -> None:
    issues = STRUCTURAL.validate("const s = `unclosed")
    assert "unterminated template literal" in issues[0].message


# ---------------------------------------------------------------------------
# esprima валидатор (точная проверка синтаксиса)
# ---------------------------------------------------------------------------

@esprima_required
def test_esprima_valid_code() -> None:
    assert ESPRIMA.validate("const x = 1;\nconsole.log(x);") == []


@esprima_required
def test_esprima_reports_syntax_error_with_location() -> None:
    issues = ESPRIMA.validate("const x = ;")
    assert issues
    assert issues[0].line == 1


@esprima_required
def test_esprima_accepts_module_syntax() -> None:
    assert ESPRIMA.validate("export const x = 1;") == []


# ---------------------------------------------------------------------------
# validate_ai_output — связка извлечения и проверки
# ---------------------------------------------------------------------------

def test_validate_ok_with_structural() -> None:
    result = validate_ai_output("```js\nfoo();\n```", validator=STRUCTURAL)
    assert result.is_valid is True
    assert result.reason == "ok"
    assert result.code == "foo();"
    assert result.validator == "structural"


def test_validate_empty_response() -> None:
    result = validate_ai_output("", validator=STRUCTURAL)
    assert result.is_valid is False
    assert result.reason == "empty"
    assert result.error_summary()


def test_validate_no_code() -> None:
    result = validate_ai_output("```js\n```", validator=STRUCTURAL)
    assert result.is_valid is False
    assert result.reason == "no_code"


def test_validate_syntax_error() -> None:
    result = validate_ai_output("```js\nfoo(\n```", validator=STRUCTURAL)
    assert result.is_valid is False
    assert result.reason == "syntax"
    assert "syntax errors" in result.error_summary()


# ---------------------------------------------------------------------------
# generate_validated_code — repair-цикл с retry
# ---------------------------------------------------------------------------

def test_repair_succeeds_first_attempt() -> None:
    calls: list = []

    def regenerate(prompt, last):
        calls.append(last)
        return "```js\nok();\n```"

    result = generate_validated_code(
        "do x", regenerate, validator=STRUCTURAL, max_attempts=3
    )
    assert result.is_valid is True
    assert result.attempt == 1
    assert calls == [None]


def test_repair_retries_with_error_then_succeeds() -> None:
    responses = ["```js\nbroken(\n```", "```js\nfixed();\n```"]
    seen_feedback: list = []

    def regenerate(prompt, last):
        seen_feedback.append(last)
        return responses.pop(0)

    result = generate_validated_code(
        "do x", regenerate, validator=STRUCTURAL, max_attempts=3
    )
    assert result.is_valid is True
    assert result.attempt == 2
    # На второй попытке regenerate получает предыдущий неуспешный результат.
    assert seen_feedback[0] is None
    assert seen_feedback[1] is not None
    assert seen_feedback[1].reason == "syntax"


def test_repair_exhausts_attempts() -> None:
    def regenerate(prompt, last):
        return "```js\nstill_broken(\n```"

    with pytest.raises(AIRepairFailed) as exc_info:
        generate_validated_code(
            "do x", regenerate, validator=STRUCTURAL, max_attempts=2
        )
    assert exc_info.value.attempts == 2
    assert exc_info.value.last_result is not None
    assert exc_info.value.last_result.reason == "syntax"


def test_repair_rejects_invalid_max_attempts() -> None:
    with pytest.raises(ValueError):
        generate_validated_code("x", lambda p, last: "", max_attempts=0)
