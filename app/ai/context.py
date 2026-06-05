"""Построение контекста Notebook для передачи в LLM (issue #124).

Перед генерацией кода по Prompt Cell модели полезно «видеть» предыдущие ячейки
notebook: пояснения в markdown, ранее написанный код и результаты его
выполнения (outputs). Этот модуль собирает такой контекст в детерминированный
текст, пригодный для подстановки в промпт.

Связь с issue #125: ``NotebookContext.to_prompt()`` формирует контекстную часть
промпта, которая передаётся в ``generate_validated_code`` (Prompt -> LLM ->
Validator -> Code Cell).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Значения по умолчанию для лимитов (защита от раздувания промпта).
DEFAULT_MAX_CELLS = 20
DEFAULT_MAX_SOURCE_CHARS = 2000
DEFAULT_MAX_OUTPUT_CHARS = 1000

_TRUNCATION_MARKER = "\n… [truncated]"

# Сопоставление языка ячейки fenced-метке markdown.
_FENCE_LANG = {"code": "js", "markdown": "markdown", "raw": "text"}


def _truncate(text: str, limit: int | None) -> tuple[str, bool]:
    """Усечь текст до ``limit`` символов. Возврат (текст, был_ли_усечён)."""
    if limit is None or limit < 0 or len(text) <= limit:
        return text, False
    return text[:limit].rstrip() + _TRUNCATION_MARKER, True


def render_output(output: Any) -> str:
    """Привести output ячейки к текстовому представлению для промпта.

    Поддерживает типы из модели UI (``app/../model/types.ts``):
    ``stream`` (stdout/stderr), ``execute_result`` и ``error``. Неизвестные или
    отсутствующие outputs дают пустую строку.
    """
    if not isinstance(output, dict):
        return ""

    out_type = output.get("type")
    if out_type == "stream":
        text = str(output.get("text", ""))
        stream = output.get("stream")
        if stream == "stderr" and text.strip():
            return f"[stderr] {text.strip()}"
        return text.strip()
    if out_type == "execute_result":
        return str(output.get("text", "")).strip()
    if out_type == "error":
        ename = str(output.get("ename", "Error")).strip()
        evalue = str(output.get("evalue", "")).strip()
        header = f"{ename}: {evalue}".strip().rstrip(":")
        return f"[error] {header}".strip()
    return ""


@dataclass(frozen=True)
class ContextCell:
    """Одна ячейка, включённая в контекст."""

    index: int
    id: str
    type: str
    source: str
    output: str = ""
    source_truncated: bool = False
    output_truncated: bool = False

    @property
    def fence_lang(self) -> str:
        return _FENCE_LANG.get(self.type, "")

    def to_prompt(self) -> str:
        """Markdown-представление ячейки для промпта."""
        header = f"### Cell {self.index} [{self.type}]"
        if self.type == "markdown":
            body = self.source if self.source.strip() else "_(empty)_"
            return f"{header}\n{body}"

        lang = self.fence_lang
        code = self.source if self.source.strip() else ""
        parts = [header, f"```{lang}\n{code}\n```"]
        if self.output:
            parts.append(f"Output:\n```\n{self.output}\n```")
        return "\n".join(parts)


@dataclass(frozen=True)
class NotebookContext:
    """Результат сборки контекста notebook."""

    cells: tuple[ContextCell, ...]
    total_cells: int
    included_cells: int
    truncated: bool
    target_cell_id: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.cells

    def to_prompt(self, *, header: str = "Notebook context (previous cells)") -> str:
        """Собрать текст контекста для подстановки в промпт LLM."""
        if not self.cells:
            return ""
        body = "\n\n".join(cell.to_prompt() for cell in self.cells)
        return f"## {header}\n\n{body}"


def _cell_source(cell: dict[str, Any]) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):  # некоторые форматы хранят source построчно
        source = "".join(str(line) for line in source)
    return str(source)


def build_context(
    cells: list[dict[str, Any]],
    *,
    target_cell_id: str | None = None,
    include_outputs: bool = True,
    include_markdown: bool = True,
    include_raw: bool = False,
    max_cells: int | None = DEFAULT_MAX_CELLS,
    max_source_chars: int | None = DEFAULT_MAX_SOURCE_CHARS,
    max_output_chars: int | None = DEFAULT_MAX_OUTPUT_CHARS,
) -> NotebookContext:
    """Собрать контекст из предыдущих ячеек notebook.

    Args:
        cells: ячейки notebook (dict-и с ключами ``id``, ``type``, ``source`` и,
            для code-ячеек, ``output``).
        target_cell_id: id Prompt Cell. Включаются только ячейки **до** неё.
            Если ``None`` — берутся все ячейки.
        include_outputs: включать ли результаты выполнения code-ячеек.
        include_markdown: включать ли markdown-ячейки.
        include_raw: включать ли raw-ячейки (по умолчанию пропускаются).
        max_cells: максимум последних включаемых ячеек (``None`` — без лимита).
        max_source_chars: лимит длины source на ячейку (``None`` — без лимита).
        max_output_chars: лимит длины output на ячейку (``None`` — без лимита).
    """
    total = len(cells)

    # Ячейки строго до целевой (Prompt Cell).
    preceding: list[dict[str, Any]] = []
    for cell in cells:
        if target_cell_id is not None and cell.get("id") == target_cell_id:
            break
        preceding.append(cell)

    # Отбор по типу.
    selected: list[dict[str, Any]] = []
    for cell in preceding:
        cell_type = cell.get("type")
        if cell_type == "markdown" and not include_markdown:
            continue
        if cell_type == "raw" and not include_raw:
            continue
        if cell_type not in ("code", "markdown", "raw"):
            continue
        selected.append(cell)

    truncated = False

    # Ограничение количества: берём последние max_cells (ближайшие к Prompt Cell).
    if max_cells is not None and len(selected) > max_cells:
        selected = selected[-max_cells:]
        truncated = True

    context_cells: list[ContextCell] = []
    for index, cell in enumerate(selected, start=1):
        cell_type = str(cell.get("type", ""))
        source, src_trunc = _truncate(_cell_source(cell), max_source_chars)

        output_text = ""
        out_trunc = False
        if include_outputs and cell_type == "code":
            rendered = render_output(cell.get("output"))
            output_text, out_trunc = _truncate(rendered, max_output_chars)

        truncated = truncated or src_trunc or out_trunc
        context_cells.append(
            ContextCell(
                index=index,
                id=str(cell.get("id", "")),
                type=cell_type,
                source=source,
                output=output_text,
                source_truncated=src_trunc,
                output_truncated=out_trunc,
            )
        )

    return NotebookContext(
        cells=tuple(context_cells),
        total_cells=total,
        included_cells=len(context_cells),
        truncated=truncated,
        target_cell_id=target_cell_id,
    )
