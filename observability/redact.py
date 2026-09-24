"""Mask secrets before anything reaches a span, an event, an artifact or a trace file."""

from __future__ import annotations

import re
from typing import Any

MASK = "[REDACTED]"

# Order matters: specific token shapes first, then generic key=value / key: value pairs.
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{16,}"), MASK),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), MASK),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), MASK),
    (re.compile(r"(?i)\b(Bearer)\s+[A-Za-z0-9._~+/\-]+=*"), rf"\1 {MASK}"),
    (
        re.compile(
            r"""(?ix)
            \b([\w.\-]*(?:api[_-]?key|secret|token|password|passwd|pwd)[\w.\-]*)  # key name
            (["']?\s*[:=]\s*["']?)                                           # separator
            ([^\s"',;&]+)                                                     # value
            """
        ),
        rf"\1\2{MASK}",
    ),
)


def redact(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


def redact_value(value: Any) -> Any:
    """Recursively redact strings inside str / list / tuple / dict values."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, (list, tuple)):
        return type(value)(redact_value(v) for v in value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    return value
