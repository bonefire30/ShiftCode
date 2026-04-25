"""
LangChain tools for project-level migration agents.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from langchain_core.tools import tool

from learnings import record_learning as record_learning_impl
from learnings import search_learnings as search_learnings_impl
from mcp_bridge import mcp_invoke, mcp_list_servers
from skills_loader import list_skills, load_skill


def _rel_norm(path: str) -> str:
    rel = (path or "").strip().replace("\\", "/")
    rel = rel.replace("..", "").lstrip("/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel if rel else "."


def _under_workspace(path: str, root: Path) -> Path | str:
    rel = _rel_norm(path)
    full = (root / rel).resolve()
    if not str(full).startswith(str(root.resolve())):
        return f"Error: path escapes workspace: {path!r}"
    return full


def build_project_file_tools(go_output_dir: Path, output_file: str) -> list:
    """
    Tools for a single file inside a project-level Go output directory.
    """
    root = go_output_dir.resolve()
    if not root.is_dir():
        root.mkdir(parents=True, exist_ok=True)
    target_rel = _rel_norm((output_file or "main.go").replace("\\", "/"))

    @tool
    def read_file(relative_path: str) -> str:
        """Read a file under the project output directory."""
        f = _under_workspace(relative_path, root)
        if isinstance(f, str):
            return f
        if not f.is_file():
            return f"Error: not a file: {relative_path!r}"
        return f.read_text(encoding="utf-8", errors="replace")

    @tool
    def write_file(relative_path: str, content: str) -> str:
        """Write or overwrite a file under the project output directory."""
        f = _under_workspace(relative_path, root)
        if isinstance(f, str):
            return f
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {relative_path!r}."

    @tool
    def edit_file(relative_path: str, old_str: str, new_str: str) -> str:
        """Replace exactly one occurrence of old_str in a file."""
        f = _under_workspace(relative_path, root)
        if isinstance(f, str):
            return f
        if not f.is_file():
            return f"Error: not a file: {relative_path!r}"
        text = f.read_text(encoding="utf-8", errors="replace")
        count = text.count(old_str)
        if count == 0:
            return "Error: old_str not found."
        if count > 1:
            return f"Error: old_str is not unique ({count} matches)."
        f.write_text(text.replace(old_str, new_str, 1), encoding="utf-8")
        return f"Replaced 1 occurrence in {relative_path!r}."

    @tool
    def list_dir(relative_path: str = "") -> str:
        """List files and subdirectories. Empty string means project root."""
        f = _under_workspace((relative_path or ".").replace("\\", "/"), root)
        if isinstance(f, str):
            return f
        if not f.is_dir():
            return f"Error: not a directory: {relative_path!r}"
        lines: list[str] = []
        for p in sorted(f.iterdir()):
            kind = "dir" if p.is_dir() else "file"
            lines.append(f"{kind}  {p.name}")
        return "\n".join(lines) if lines else "(empty directory)"

    @tool
    def run_go_build() -> str:
        """
        Run `go build ./...` from the project output root.
        """
        _ = target_rel
        try:
            p = subprocess.run(
                ["go", "build", "./..."],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=600,
            )
        except FileNotFoundError as e:
            return f"Error: {e} (is `go` on PATH?)"
        except subprocess.TimeoutExpired:
            return "Error: go build ./... timed out (600s)."
        out = (p.stdout or "") + (p.stderr or "")
        if p.returncode == 0:
            return "OK: go build ./... succeeded.\n" + (out.strip() or "")
        return (
            f"FAILED: go build ./... exit {p.returncode}.\n"
            f"(Assigned file: {target_rel})\n{out[:12_000]}"
        )

    @tool
    def record_learning(topic: str, content: str) -> str:
        """Store a long-term migration learning."""
        return record_learning_impl(topic, content)

    @tool
    def search_learnings(query: str) -> str:
        """Search past learnings by keyword."""
        return search_learnings_impl(query)

    @tool
    def load_skill_tool(skill_name: str) -> str:
        """Load a SKILL.md SOP from the skills directory."""
        return load_skill(skill_name)

    @tool
    def list_available_skills() -> str:
        """List skills with SKILL.md under the repository skills tree."""
        return list_skills()

    @tool
    def mcp_query(tool_name: str, arguments_json: str) -> str:
        """
        Call a configured stdio MCP server tool.
        """
        return mcp_invoke(tool_name, arguments_json)

    @tool
    def mcp_status() -> str:
        """Show MCP stdio environment status."""
        return mcp_list_servers()

    return [
        read_file,
        write_file,
        edit_file,
        list_dir,
        run_go_build,
        record_learning,
        search_learnings,
        load_skill_tool,
        list_available_skills,
        mcp_query,
        mcp_status,
    ]


def build_module_translate_tools(
    go_output_dir: Path,
    module_targets: list[tuple[str, str, str]],
) -> list:
    """
    Multi-file module migration tools.
    """
    root = go_output_dir.resolve()
    if not root.is_dir():
        root.mkdir(parents=True, exist_ok=True)
    written_files: set[str] = set()
    primary = (
        _rel_norm((module_targets[0][1] or "main.go").replace("\\", "/"))
        if module_targets
        else "main.go"
    )

    @tool
    def list_module_files() -> str:
        """List Java->Go file assignments in this module."""
        lines = [f"- {jr!r}  ->  {gr!r}  (Go package: {pkg!r})" for jr, gr, pkg in module_targets]
        return "\n".join(lines) if lines else "(empty module)"

    @tool
    def read_file(relative_path: str) -> str:
        """Read a file under the project output directory."""
        f = _under_workspace(relative_path, root)
        if isinstance(f, str):
            return f
        if not f.is_file():
            return f"Error: not a file: {relative_path!r}"
        return f.read_text(encoding="utf-8", errors="replace")

    @tool
    def write_file(relative_path: str, content: str) -> str:
        """Write or overwrite a file under the project output directory."""
        rel = _rel_norm(relative_path)
        f = _under_workspace(rel, root)
        if isinstance(f, str):
            return f
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
        written_files.add(rel)
        return f"Wrote {len(content)} bytes to {relative_path!r}."

    @tool
    def edit_file(relative_path: str, old_str: str, new_str: str) -> str:
        """Replace exactly one occurrence of old_str in a file."""
        rel = _rel_norm(relative_path)
        f = _under_workspace(rel, root)
        if isinstance(f, str):
            return f
        if not f.is_file():
            return f"Error: not a file: {relative_path!r}"
        text = f.read_text(encoding="utf-8", errors="replace")
        count = text.count(old_str)
        if count == 0:
            return "Error: old_str not found."
        if count > 1:
            return f"Error: old_str is not unique ({count} matches)."
        f.write_text(text.replace(old_str, new_str, 1), encoding="utf-8")
        written_files.add(rel)
        return f"Replaced 1 occurrence in {relative_path!r}."

    @tool
    def list_written_files() -> str:
        """Return normalized relative paths written/edited in this round as JSON array."""
        return json.dumps(sorted(written_files), ensure_ascii=False)

    @tool
    def list_dir(relative_path: str = "") -> str:
        """List files and subdirectories. Empty string means project root."""
        f = _under_workspace((relative_path or ".").replace("\\", "/"), root)
        if isinstance(f, str):
            return f
        if not f.is_dir():
            return f"Error: not a directory: {relative_path!r}"
        lines: list[str] = []
        for p in sorted(f.iterdir()):
            kind = "dir" if p.is_dir() else "file"
            lines.append(f"{kind}  {p.name}")
        return "\n".join(lines) if lines else "(empty directory)"

    @tool
    def run_go_build() -> str:
        """Run `go build ./...` from the project output root."""
        _ = primary
        try:
            p = subprocess.run(
                ["go", "build", "./..."],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=600,
            )
        except FileNotFoundError as e:
            return f"Error: {e} (is `go` on PATH?)"
        except subprocess.TimeoutExpired:
            return "Error: go build ./... timed out (600s)."
        out = (p.stdout or "") + (p.stderr or "")
        if p.returncode == 0:
            return "OK: go build ./... succeeded.\n" + (out.strip() or "")
        return (
            f"FAILED: go build ./... exit {p.returncode}.\n"
            f"(Module primary: {primary})\n{out[:12_000]}"
        )

    @tool
    def record_learning(topic: str, content: str) -> str:
        """Store a long-term migration learning."""
        return record_learning_impl(topic, content)

    @tool
    def search_learnings(query: str) -> str:
        """Search past learnings by keyword."""
        return search_learnings_impl(query)

    @tool
    def load_skill_tool(skill_name: str) -> str:
        """Load a SKILL.md SOP from the skills directory."""
        return load_skill(skill_name)

    @tool
    def list_available_skills() -> str:
        """List skills with SKILL.md under the repository skills tree."""
        return list_skills()

    @tool
    def mcp_query(tool_name: str, arguments_json: str) -> str:
        """Call a configured stdio MCP server tool."""
        return mcp_invoke(tool_name, arguments_json)

    @tool
    def mcp_status() -> str:
        """Show MCP stdio environment status."""
        return mcp_list_servers()

    return [
        list_module_files,
        read_file,
        write_file,
        edit_file,
        list_written_files,
        list_dir,
        run_go_build,
        record_learning,
        search_learnings,
        load_skill_tool,
        list_available_skills,
        mcp_query,
        mcp_status,
    ]


def _is_test_go_path(rel: str) -> bool:
    norm = (rel or "").replace("\\", "/").strip()
    return norm.endswith("_test.go") and not norm.startswith("..")


def _count_test_go_files(root: Path) -> int:
    return sum(1 for p in root.rglob("*_test.go") if p.is_file())


def build_test_gen_tools(go_output_dir: Path) -> list:
    """
    Test-generation tools for project-level migration.
    """
    root = go_output_dir.resolve()
    if not root.is_dir():
        root.mkdir(parents=True, exist_ok=True)
    written_files: set[str] = set()

    @tool
    def read_file(relative_path: str) -> str:
        """Read a file under the project output directory."""
        f = _under_workspace(relative_path, root)
        if isinstance(f, str):
            return f
        if not f.is_file():
            return f"Error: not a file: {relative_path!r}"
        return f.read_text(encoding="utf-8", errors="replace")

    @tool
    def list_dir(relative_path: str = "") -> str:
        """List files and subdirectories. Empty string means project root."""
        f = _under_workspace((relative_path or ".").replace("\\", "/"), root)
        if isinstance(f, str):
            return f
        if not f.is_dir():
            return f"Error: not a directory: {relative_path!r}"
        lines: list[str] = []
        for p in sorted(f.iterdir()):
            kind = "dir" if p.is_dir() else "file"
            lines.append(f"{kind}  {p.name}")
        return "\n".join(lines) if lines else "(empty directory)"

    @tool
    def write_test_file(relative_path: str, content: str) -> str:
        """Write a Go test file (*_test.go only) under the project root."""
        rel = (relative_path or "").strip().replace("\\", "/")
        if not _is_test_go_path(rel):
            return "Error: only paths ending in _test.go are allowed for write_test_file."
        f = _under_workspace(rel, root)
        if isinstance(f, str):
            return f
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
        written_files.add(_rel_norm(rel))
        return f"Wrote {len(content)} bytes to {relative_path!r}."

    @tool
    def edit_test_file(relative_path: str, old_str: str, new_str: str) -> str:
        """Edit a Go test file (*_test.go only)."""
        rel = (relative_path or "").strip().replace("\\", "/")
        if not _is_test_go_path(rel):
            return "Error: only paths ending in _test.go are allowed for edit_test_file."
        f = _under_workspace(rel, root)
        if isinstance(f, str):
            return f
        if not f.is_file():
            return f"Error: not a file: {relative_path!r}"
        text = f.read_text(encoding="utf-8", errors="replace")
        count = text.count(old_str)
        if count == 0:
            return "Error: old_str not found."
        if count > 1:
            return f"Error: old_str is not unique ({count} matches)."
        f.write_text(text.replace(old_str, new_str, 1), encoding="utf-8")
        written_files.add(_rel_norm(rel))
        return f"Replaced 1 occurrence in {relative_path!r}."

    @tool
    def list_written_files() -> str:
        """Return normalized relative paths written/edited in this round as JSON array."""
        return json.dumps(sorted(written_files), ensure_ascii=False)

    @tool
    def run_go_tests_only() -> str:
        """Run `go test -count=1 -v ./...` from the project output root."""
        if _count_test_go_files(root) == 0:
            return "FAILED: no generated test files found."
        try:
            p = subprocess.run(
                ["go", "test", "-count=1", "-v", "./..."],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=600,
            )
        except FileNotFoundError as e:
            return f"Error: {e} (is `go` on PATH?)"
        except subprocess.TimeoutExpired:
            return "Error: go test timed out (600s)."
        out = (p.stdout or "") + (p.stderr or "")
        if p.returncode == 0:
            return "OK: all tests passed.\n" + (out[:12_000] or "")
        return f"FAILED: go test exit {p.returncode}.\n{out[:12_000]}"

    @tool
    def record_learning(topic: str, content: str) -> str:
        """Store a long-term migration learning."""
        return record_learning_impl(topic, content)

    @tool
    def search_learnings(query: str) -> str:
        """Search past learnings by keyword."""
        return search_learnings_impl(query)

    return [
        read_file,
        list_dir,
        write_test_file,
        edit_test_file,
        list_written_files,
        run_go_tests_only,
        record_learning,
        search_learnings,
    ]
