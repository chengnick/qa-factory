"""Mask secrets before anything reaches a span, an event, an artifact or a trace file."""

from __future__ import annotations

import re
from typing import Any

MASK = "[REDACTED]"
USER_MASK = "[USER]"  # replaces the account name in a home-directory path

# Order matters: specific token shapes first, then generic key=value / key: value pairs.
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{16,}"), MASK),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), MASK),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), MASK),  # Google API key
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
    # Home directories: the account name in a local path is personal data (Phase 2R logs held C:\Users\<name>\...).
    (re.compile(r"(?i)\b([A-Z]:(?:\\{1,2}|/)(?:Users|Documents and Settings)(?:\\{1,2}|/))[^\\/:*?\"<>|\r\n]+"), rf"\1{USER_MASK}"),
    (re.compile(r"(?<![\w.])(/home/|/Users/)[^/\s\"']+"), rf"\1{USER_MASK}"),
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


# Credential shapes used to *detect* a leak (e.g. before committing run artifacts). Narrower than the
# masking rules above, which also mask any `*token*=value` pair and would flag metric names like
# "input_tokens".
SECRET_SHAPES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"(?i)\bBearer\s+(?!\[REDACTED\])[A-Za-z0-9._~+/\-]{16,}"),
    re.compile(r"""(?i)\b[\w.\-]*(?:api[_-]?key|secret|password)[\w.\-]*["']?\s*[:=]\s*["']?(?!\[REDACTED\])[^\s"',;&]{8,}"""),
)


def find_secret(text: str) -> str | None:
    """Return the first credential-shaped match (for reporting where), or None."""
    for pattern in SECRET_SHAPES:
        if m := pattern.search(text):
            return m.group(0)
    return None
