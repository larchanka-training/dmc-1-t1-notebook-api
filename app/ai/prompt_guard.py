"""Lightweight prompt injection detection.

Defense-in-depth alongside the system prompt. Not a complete guard on its own —
a determined attacker can work around pattern matching. The system prompt is the
primary defense; this catches the most common off-the-shelf injection attempts.
"""

from __future__ import annotations

import re

from fastapi import HTTPException

# Common patterns used to hijack or redirect model instructions.
_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above|your)\s+instructions",
    r"disregard\s+(all\s+)?(previous|prior|above|your)\s+instructions",
    r"forget\s+(all\s+)?(previous|prior|above|your)\s+instructions",
    r"new\s+instructions\s*:",
    r"you\s+are\s+now\s+(a|an|the)\b",
    r"act\s+as\s+(a|an|the|if)\b",
    r"pretend\s+(you\s+are|to\s+be)\b",
    r"(reveal|print|show|output|repeat)\s+(your\s+)?(system\s+)?prompt",
    r"\bdan\s+mode\b",
    r"\bjailbreak\b",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _PATTERNS]


def check_prompt(prompt: str) -> None:
    """Raise HTTP 400 if prompt contains injection patterns."""
    for pattern in _COMPILED:
        if pattern.search(prompt):
            raise HTTPException(
                status_code=400,
                detail="Prompt contains disallowed content",
            )
