"""
Long-term project learnings (JSON store, substring search, append).
Agent tools: `record_learning`, `search_learnings` (see agent_tools).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_LEARNINGS_PATH = ROOT / "learnings.json"


@dataclass
class LearningEntry:
    topic: str
    content: str
    ts: str


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"entries": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"entries": []}


def _save(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def record_learning(topic: str, content: str, *, path: Path | None = None) -> str:
    """Append one learning. Returns a short status line."""
    p = path or DEFAULT_LEARNINGS_PATH
    data = _load(p)
    ent = {
        "topic": topic.strip()[:200],
        "content": content.strip()[:20000],
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    data.setdefault("entries", []).append(ent)
    _save(p, data)
    return f"recorded: {ent['topic']!r} ({ent['ts']})"


def search_learnings(
    query: str,
    *,
    path: Path | None = None,
    limit: int = 12,
) -> str:
    """Case-insensitive substring search over topic+content."""
    p = path or DEFAULT_LEARNINGS_PATH
    data = _load(p)
    q = query.strip().lower()
    if not q:
        return "Provide a non-empty search query."
    out: list[str] = []
    for ent in reversed(data.get("entries", [])):
        topic = str(ent.get("topic", ""))
        content = str(ent.get("content", ""))
        hay = (topic + "\n" + content).lower()
        if q in hay:
            out.append(
                f"[{ent.get('ts', '')}] {topic}:\n{content[:500]}{'...' if len(content) > 500 else ''}"
            )
        if len(out) >= limit:
            break
    if not out:
        return f"No learnings match {query!r}."
    return "\n\n---\n\n".join(out)
