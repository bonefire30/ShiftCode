"""
Global symbol table: Java types and translated Go snippets for cross-file translator context.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from java_ast import JavaFileInfo


@dataclass
class SymbolEntry:
    java_fqn: str  # e.g. com.example.UserService
    java_simple: str
    package: str
    go_package_hint: str
    """Short summary of methods for LLM (from Java)."""
    java_signatures: list[str] = field(default_factory=list)
    """After translation: first ~2k of Go file or stub."""
    go_code_snippet: str = ""


class SymbolTable:
    """
    ClassName / FQN -> SymbolEntry; serializable via to_dict / from_dict.
    """

    def __init__(self) -> None:
        self._by_simple: dict[str, SymbolEntry] = {}
        self._by_fqn: dict[str, SymbolEntry] = {}

    def register(self, info: JavaFileInfo) -> None:
        for c in info.classes:
            fqn = f"{info.package}.{c}" if info.package else c
            e = SymbolEntry(
                java_fqn=fqn,
                java_simple=c,
                package=info.package,
                go_package_hint=_go_package_from_java_path(info.path),
                java_signatures=info.methods[:40],
            )
            self._by_simple[c] = e
            self._by_fqn[fqn] = e

    def register_go(self, class_name: str, go_code: str) -> None:
        e = self._by_simple.get(class_name)
        if e:
            e.go_code_snippet = go_code[:8000]
        for k, v in list(self._by_fqn.items()):
            if v.java_simple == class_name:
                v.go_code_snippet = go_code[:8000]

    def context_for(self, file_info: JavaFileInfo, max_chars: int = 12000) -> str:
        """Text block for translator prompt: symbols this file might depend on."""
        lines: list[str] = []
        seen: set[str] = set()
        for imp in file_info.imports:
            sn = imp.split(".")[-1]
            ent = self._by_simple.get(sn)
            if ent and ent.java_simple not in seen:
                seen.add(ent.java_simple)
                lines.append(
                    f"### {ent.java_simple} ({ent.java_fqn})\n"
                    f"- Go package hint: `{ent.go_package_hint}`\n"
                    f"- Java methods (signatures): {ent.java_signatures[:8]!r}\n"
                )
                if ent.go_code_snippet:
                    lines.append(
                        "Go code (current workspace):\n```go\n"
                        + ent.go_code_snippet[:4000]
                        + "\n```\n"
                    )
        for tok in re.findall(r"\b([A-Z][a-zA-Z0-9_]*)\b", file_info.source_text):
            if tok in seen or tok in (
                "String",
                "Object",
                "Integer",
                "Long",
                "System",
                "Class",
            ):
                continue
            ent = self._by_simple.get(tok)
            if ent and ent.java_simple not in seen:
                seen.add(ent.java_simple)
                lines.append(
                    f"### {ent.java_simple}\n- signatures: {ent.java_signatures[:5]!r}\n"
                )
                if ent.go_code_snippet:
                    lines.append(
                        "```go\n" + ent.go_code_snippet[:2000] + "\n```\n"
                    )
        text = "\n".join(lines)
        if len(text) > max_chars:
            return text[:max_chars] + "\n...[truncated]"
        return text

    @staticmethod
    def java_to_go_types() -> dict[str, str]:
        return {
            "java.util.List": "slice []T (use []T in Go)",
            "java.util.Map": "map[K]V",
            "java.util.Set": "map[T]struct{} or []T",
            "java.util.Optional": "value, ok := ... or *T",
            "java.lang.String": "string",
            "java.lang.Integer": "int",
            "java.lang.Long": "int64",
            "java.lang.Boolean": "bool",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "by_simple": {k: asdict(v) for k, v in self._by_simple.items()},
            "by_fqn": {k: asdict(v) for k, v in self._by_fqn.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SymbolTable:
        t = cls()
        for k, row in (data.get("by_simple") or {}).items():
            t._by_simple[k] = SymbolEntry(**row)
        for k, row in (data.get("by_fqn") or {}).items():
            t._by_fqn[k] = SymbolEntry(**row)
        return t

    def merge_from(self, other: SymbolTable) -> None:
        self._by_simple.update(other._by_simple)
        self._by_fqn.update(other._by_fqn)

    def get(self, simple_name: str) -> SymbolEntry | None:
        return self._by_simple.get(simple_name)


def _go_package_from_java_path(java_path: str) -> str:
    p = java_path.replace("\\", "/")
    parts = p.split("/")
    if len(parts) >= 2:
        return parts[-2].lower()
    return "main"


def symbol_table_from_json(s: str | None) -> SymbolTable:
    if not s:
        return SymbolTable()
    try:
        return SymbolTable.from_dict(json.loads(s))
    except (json.JSONDecodeError, TypeError, KeyError):
        return SymbolTable()
