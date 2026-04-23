"""
Centralized logging: console (colored) + per-run JSON line files in run_logs/.

Per-run files are attached via attach_per_run_file_handler() during a migration
or resume; no global shiftcode.log roll.

Environment:
  LOG_LEVEL: DEBUG, INFO, WARNING, ERROR (default: INFO)
"""

from __future__ import annotations

import contextvars
import datetime
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, MutableMapping

ROOT = Path(__file__).resolve().parent
RUN_LOGS = ROOT / "run_logs"
RUN_LOGS.mkdir(parents=True, exist_ok=True)

_workflow_thread_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "workflow_thread_id", default="?"
)
_setup_done = False

# --- ANSI (Windows 10+ and POSIX); optional dim/faint for logger name ---

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_LEVEL_COLORS: dict[str, str] = {
    "DEBUG": "\033[36m",  # cyan
    "INFO": "\033[32m",  # green
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[35m",
}
_USE_ANSI = sys.stderr.isatty() and os.environ.get("NO_COLOR", "").strip() == ""


def get_workflow_thread_id() -> str:
    return _workflow_thread_id.get()


def set_workflow_thread_id(tid: str) -> contextvars.Token[str]:
    return _workflow_thread_id.set(tid)


def reset_workflow_thread_id(token: contextvars.Token[str]) -> None:
    _workflow_thread_id.reset(token)


class _JsonFormatter(logging.Formatter):
    """One JSON object per line for file sink."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        n = getattr(record, "node", None)
        t = getattr(record, "tid", None)
        if n is not None:
            payload["node"] = n
        if t is not None:
            payload["thread_id"] = t
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False) + "\n"


class _ColorConsoleFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s.%(msecs)03d [%(levelname)s] "
            f"{_DIM}%(name)s{_RESET} %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        orig = super().format(record)
        if not _USE_ANSI:
            return orig
        c = _LEVEL_COLORS.get(record.levelname, "")
        if not c:
            return orig
        old = f"[{record.levelname}]"
        new = f"{_BOLD}{c}[{record.levelname}]{_RESET}"
        return orig.replace(old, new, 1)


class _NodeLoggerAdapter(logging.LoggerAdapter[logging.Logger]):
    """Prefix messages with [node|tid] and pass node/tid on LogRecord for JSON."""

    def __init__(self, logger: logging.Logger, node: str, thread_id: str | None) -> None:
        super().__init__(logger, {})
        self.node = node
        self.tid = thread_id

    def process(
        self, msg: str, kwargs: Any
    ) -> tuple[str, Any]:
        n = self.node or "?"
        t = (self.tid or get_workflow_thread_id()) or "?"
        if not isinstance(kwargs, dict):
            kwargs = {}
        else:
            kwargs = {**kwargs}
        ex = dict(kwargs.get("extra") or {})
        ex.setdefault("node", n)
        ex.setdefault("tid", t)
        kwargs["extra"] = ex
        return f"[{n}|{t}] {msg}", kwargs


def node_logger(node: str, thread_id: str | None = None) -> _NodeLoggerAdapter:
    return _NodeLoggerAdapter(
        logging.getLogger("shiftcode.workflow"), node, thread_id
    )


def llm_logger(node: str, thread_id: str | None = None) -> _NodeLoggerAdapter:
    return _NodeLoggerAdapter(logging.getLogger("shiftcode.llm"), node, thread_id)


def _resolve_log_level(
    level: int | str | None,
) -> int:
    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO").upper()
    if isinstance(level, str):
        level = getattr(logging, level, logging.INFO)
    if not isinstance(level, int):
        level = logging.INFO  # type: ignore[unreachable]
    return level


def attach_per_run_file_handler(
    *,
    thread_id: str,
    prefix: str = "migration",
    level: int | str | None = None,
) -> logging.FileHandler:
    """
    Append a FileHandler to the root logger; one JSON line per log record.
    Filename: {prefix}_YYYYMMDD_HHMMSS_{short_id}.log
    """
    resolved = _resolve_log_level(level)
    RUN_LOGS.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tail = thread_id
    if tail.startswith("pm-"):
        tail = tail[3:]
    short = tail[:12] if len(tail) > 8 else (tail or "unknown")
    path = RUN_LOGS / f"{prefix}_{ts}_{short}.log"
    fh = logging.FileHandler(str(path), encoding="utf-8")
    fh.setLevel(min(resolved, logging.DEBUG))
    fh.setFormatter(_JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))
    logging.getLogger().addHandler(fh)
    return fh


def detach_per_run_file_handler(handler: logging.Handler) -> None:
    root = logging.getLogger()
    if handler in root.handlers:
        root.removeHandler(handler)
    handler.close()


def setup_logging(
    level: int | str | None = None,
    *,
    log_to_file: bool = False,
) -> None:
    """Idempotent. Console only (stderr) by default; use attach_per_run_file_handler for run files."""
    global _setup_done
    if _setup_done:
        return

    level = _resolve_log_level(level)

    root = logging.getLogger()
    root.setLevel(min(level, logging.DEBUG))

    # Clear default handlers (if any) only on first run
    root.handlers.clear()

    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(level)
    ch.setFormatter(_ColorConsoleFormatter() if _USE_ANSI else logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)8s] %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(ch)

    if log_to_file:
        # Legacy: opt-in global file (same process); prefer per-run attach instead.
        fh = logging.FileHandler(
            str(RUN_LOGS / "shiftcode.log"), encoding="utf-8", mode="a"
        )
        fh.setLevel(min(level, logging.DEBUG))
        fh.setFormatter(_JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))
        root.addHandler(fh)

    for name in ("shiftcode", "shiftcode.workflow", "shiftcode.server", "shiftcode.llm"):
        lg = logging.getLogger(name)
        lg.setLevel(level)
        lg.propagate = True

    _setup_done = True
