import os

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("COOKIE_DOMAIN", "localhost")

from app.ai.context import (  # noqa: E402
    DEFAULT_MAX_CELLS,
    build_context,
    render_output,
)


def _code(cell_id: str, source: str, output=None) -> dict:
    cell: dict = {"id": cell_id, "type": "code", "source": source}
    if output is not None:
        cell["output"] = output
    return cell


def _md(cell_id: str, source: str) -> dict:
    return {"id": cell_id, "type": "markdown", "source": source}


# ---------------------------------------------------------------------------
# render_output — типы output из модели UI
# ---------------------------------------------------------------------------

def test_render_execute_result() -> None:
    assert render_output({"type": "execute_result", "text": "42"}) == "42"


def test_render_stream_stdout() -> None:
    assert render_output({"type": "stream", "stream": "stdout", "text": "hi\n"}) == "hi"


def test_render_stream_stderr_prefixed() -> None:
    out = render_output({"type": "stream", "stream": "stderr", "text": "warn"})
    assert out == "[stderr] warn"


def test_render_error() -> None:
    out = render_output(
        {"type": "error", "ename": "TypeError", "evalue": "x is not a function"}
    )
    assert out == "[error] TypeError: x is not a function"


def test_render_unknown_or_missing() -> None:
    assert render_output(None) == ""
    assert render_output({"type": "weird"}) == ""
    assert render_output("not a dict") == ""


# ---------------------------------------------------------------------------
# build_context — отбор предыдущих ячеек
# ---------------------------------------------------------------------------

def test_includes_only_cells_before_target() -> None:
    cells = [
        _md("m1", "# Title"),
        _code("c1", "const x = 1;"),
        _code("prompt", "// generate something"),
        _code("c2", "after"),
    ]
    ctx = build_context(cells, target_cell_id="prompt")
    assert ctx.total_cells == 4
    assert ctx.included_cells == 2
    assert [c.id for c in ctx.cells] == ["m1", "c1"]


def test_no_target_includes_all() -> None:
    cells = [_md("m1", "doc"), _code("c1", "foo();")]
    ctx = build_context(cells)
    assert ctx.included_cells == 2


def test_markdown_and_code_and_output_in_prompt() -> None:
    cells = [
        _md("m1", "# Setup"),
        _code("c1", "const x = 1;", {"type": "execute_result", "text": "1"}),
        _code("prompt", "// task"),
    ]
    prompt = build_context(cells, target_cell_id="prompt").to_prompt()
    assert "Notebook context (previous cells)" in prompt
    assert "# Setup" in prompt
    assert "```js\nconst x = 1;\n```" in prompt
    assert "Output:\n```\n1\n```" in prompt


def test_include_outputs_false_omits_output() -> None:
    cells = [_code("c1", "x", {"type": "execute_result", "text": "1"})]
    ctx = build_context(cells, include_outputs=False)
    assert ctx.cells[0].output == ""
    assert "Output:" not in ctx.to_prompt()


def test_raw_cells_skipped_by_default() -> None:
    cells = [{"id": "r1", "type": "raw", "source": "raw"}, _code("c1", "foo();")]
    ctx = build_context(cells)
    assert [c.id for c in ctx.cells] == ["c1"]


def test_markdown_excluded_when_disabled() -> None:
    cells = [_md("m1", "doc"), _code("c1", "foo();")]
    ctx = build_context(cells, include_markdown=False)
    assert [c.id for c in ctx.cells] == ["c1"]


def test_empty_notebook_yields_empty_prompt() -> None:
    ctx = build_context([])
    assert ctx.is_empty
    assert ctx.to_prompt() == ""


# ---------------------------------------------------------------------------
# Лимиты и усечение
# ---------------------------------------------------------------------------

def test_max_cells_keeps_latest() -> None:
    cells = [_code(f"c{i}", f"line{i};") for i in range(5)]
    ctx = build_context(cells, max_cells=2)
    assert ctx.truncated is True
    assert [c.id for c in ctx.cells] == ["c3", "c4"]


def test_default_max_cells_constant_applied() -> None:
    cells = [_code(f"c{i}", "x;") for i in range(DEFAULT_MAX_CELLS + 5)]
    ctx = build_context(cells)
    assert ctx.included_cells == DEFAULT_MAX_CELLS
    assert ctx.truncated is True


def test_source_truncation() -> None:
    cells = [_code("c1", "a" * 100)]
    ctx = build_context(cells, max_source_chars=10)
    assert ctx.cells[0].source_truncated is True
    assert ctx.truncated is True
    assert "[truncated]" in ctx.cells[0].source


def test_output_truncation() -> None:
    cells = [_code("c1", "x", {"type": "execute_result", "text": "b" * 100})]
    ctx = build_context(cells, max_output_chars=10)
    assert ctx.cells[0].output_truncated is True
    assert "[truncated]" in ctx.cells[0].output


def test_no_limits_when_none() -> None:
    cells = [_code(f"c{i}", "x;") for i in range(50)]
    ctx = build_context(cells, max_cells=None)
    assert ctx.included_cells == 50
    assert ctx.truncated is False


def test_source_as_list_is_joined() -> None:
    cells = [{"id": "c1", "type": "code", "source": ["a();\n", "b();"]}]
    ctx = build_context(cells)
    assert ctx.cells[0].source == "a();\nb();"
