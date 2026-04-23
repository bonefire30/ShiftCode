"""
Load SKILL.md-style documents from the repository `skills/` tree.
`SKILL_ROOT` env overrides the root directory.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_SKILL_ROOT = ROOT / "skills"


def get_skill_root() -> Path:
    env = (os.environ.get("SKILL_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    return DEFAULT_SKILL_ROOT.resolve()


def list_skills() -> str:
    root = get_skill_root()
    if not root.is_dir():
        return f"Skill root {root} not found. Create `skills/<name>/SKILL.md`."
    found: list[str] = []
    for p in sorted(root.rglob("SKILL.md")):
        rel = p.parent.relative_to(root)
        name = str(rel).replace("\\", "/") if str(rel) != "." else p.parent.name
        found.append(name)
    if not found:
        return f"No SKILL.md under {root}."
    return "Available skills: " + ", ".join(found)


def load_skill(name: str) -> str:
    """Load skill by subpath (e.g. `migration/java_to_go` or a folder name with SKILL.md)."""
    root = get_skill_root()
    name = name.strip().replace("..", "").strip("/")
    if not name:
        return "Error: empty skill name. Use list_skills or pass a name."
    cands = [
        root / name / "SKILL.md",
        root / f"{name}.md",
    ]
    for c in cands:
        if c.is_file():
            return c.read_text(encoding="utf-8")
    return f"Skill {name!r} not found. Try: {list_skills()}"

