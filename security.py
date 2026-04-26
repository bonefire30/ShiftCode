"""Small security helpers for log/report redaction."""

from __future__ import annotations

import re
from typing import Any


_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)([^\s,;\]})]+)"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)([^\s,;\]})]+)"),
    re.compile(r"(?i)((?:OPENAI|MINIMAX|DEEPSEEK|CODEX_PROXY)_API_KEY\s*[=:]\s*)([^\s,;\]})]+)"),
    re.compile(r"\bsk-[A-Za-z0-9._\-]{8,}\b"),
)


def sanitize_secret_text(value: Any) -> str:
    text = str(value or "")
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 2:
            text = pattern.sub(lambda m: m.group(1) + "[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text


def sanitize_exception(exc: BaseException) -> str:
    return sanitize_secret_text(f"{exc.__class__.__name__}: {exc}")
