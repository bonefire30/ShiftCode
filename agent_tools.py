"""
LangChain tools for the migration agent (file workspace, go test, learnings, skills, optional MCP).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from langchain_core.tools import tool
from mcp_bridge import mcp_invoke, mcp_list_servers
from learnings import record_learning, search_learnings
from skills_loader import list_skills, load_skill
from evaluate import evaluate_case, GoToolchainError

OUTPUT_FILE = "output.go"


def _rel_norm(path: str) -> str:
    r = (path or "").strip().replace("..", "").lstrip("/\\")
    return r if r else "."


def _under_workspace(path: str, root: Path) -> Path | str:
    rel = _rel_norm(path)
    full = (root / rel).resolve()
    if not str(full).startswith(str(root.resolve())):
        return f"Error: path escapes workspace: {path!r}"
    return full


def build_migration_tools(
    workspace: Path,
    case_dir: Path,
) -> list:
    root = workspace.resolve()
    case_dir = case_dir.resolve()
    if not root.is_dir():
        root.mkdir(parents=True, exist_ok=True)

    @tool
    def read_file(relative_path: str) -> str:
        """Read a file under the workspace. Use forward slashes, e.g. 'output.go'."""
        f = _under_workspace(relative_path, root)
        if isinstance(f, str):
            return f
        if not f.is_file():
            return f"Error: not a file: {relative_path!r}"
        return f.read_text(encoding="utf-8", errors="replace")

    @tool
    def write_file(relative_path: str, content: str) -> str:
        """Write or overwrite a file. Parent directories are created automatically."""
        f = _under_workspace(relative_path, root)
        if isinstance(f, str):
            return f
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {relative_path!r}."

    @tool
    def edit_file(relative_path: str, old_str: str, new_str: str) -> str:
        """Replace exactly one occurrence of old_str in the file. old_str must be unique."""
        f = _under_workspace(relative_path, root)
        if isinstance(f, str):
            return f
        if not f.is_file():
            return f"Error: not a file: {relative_path!r}"
        text = f.read_text(encoding="utf-8", errors="replace")
        c = text.count(old_str)
        if c == 0:
            return "Error: old_str not found."
        if c > 1:
            return f"Error: old_str is not unique ({c} matches)."
        f.write_text(text.replace(old_str, new_str, 1), encoding="utf-8")
        return f"Replaced 1 occurrence in {relative_path!r}."

    @tool
    def list_dir(relative_path: str = "") -> str:
        """List files and subdirectories. Empty string = workspace root."""
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
    def run_go_tests() -> str:
        """Build and run Go tests: reads workspace/output.go and benchmark expected_test.go from case_dir."""
        out = root / OUTPUT_FILE
        if not out.is_file():
            return (
                f"Error: {OUTPUT_FILE!r} not found. Use write_file to create the migrated code."
            )
        code = out.read_text(encoding="utf-8", errors="replace")
        try:
            r = evaluate_case(
                case_dir,
                code,
                repair_turns=0,
                run_lint=False,
            )
        except FileNotFoundError as e:
            return f"Error: {e}"
        except GoToolchainError as e:
            return f"Error (go): {e}"
        ok = r.compile_ok and r.test_ok
        if ok:
            return (
                "OK: all tests passed.\n"
                f"compile_ok={r.compile_ok} test_ok={r.test_ok}\n"
            )
        parts = [
            f"FAILED: compile_ok={r.compile_ok} test_ok={r.test_ok}\n",
        ]
        for label, s in [
            ("build", r.build_stderr or r.build_stdout),
            ("test", r.test_stderr or r.test_stdout),
        ]:
            if s and s.strip():
                parts.append(f"--- {label} ---\n{s[:12_000]}")
        return "\n".join(parts)

    @tool
    def record_learning(topic: str, content: str) -> str:
        """Store a long-term project learning (e.g. Java/Go idiom) for later runs."""
        return record_learning(topic, content)

    @tool
    def search_learnings(query: str) -> str:
        """Search past learnings by keyword."""
        return search_learnings(query)

    @tool
    def load_skill_tool(skill_name: str) -> str:
        """Load a SKILL.md SOP from the skills/ directory. Use for investigate/qa/migration playbooks."""
        return load_skill(skill_name)

    @tool
    def list_available_skills() -> str:
        """List skills with SKILL.md under the repository skills/ tree."""
        return list_skills()

    @tool
    def mcp_query(tool_name: str, arguments_json: str) -> str:
        """
        Call a configured stdio MCP server tool. Requires: pip install mcp and MIGRATION_MCP_COMMAND.
        arguments_json is a JSON object, e.g. {} or {"url": "https://..."}.
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
        run_go_tests,
        record_learning,
        search_learnings,
        load_skill_tool,
        list_available_skills,
        mcp_query,
        mcp_status,
    ]


def build_project_file_tools(
    go_output_dir: Path,
    output_file: str,
) -> list:
    """
    Tools for multi-file project migration: workspace = full Go project root; target file
    is the relative path under that root. Uses `go build ./...` instead of benchmark evaluate_case.
    """
    root = go_output_dir.resolve()
    if not root.is_dir():
        root.mkdir(parents=True, exist_ok=True)
    target_rel = _rel_norm((output_file or "main.go").replace("\\", "/"))

    @tool
    def read_file(relative_path: str) -> str:
        """Read a file under the project output directory. Use forward slashes, e.g. 'pkg/a.go'."""
        f = _under_workspace(relative_path, root)
        if isinstance(f, str):
            return f
        if not f.is_file():
            return f"Error: not a file: {relative_path!r}"
        return f.read_text(encoding="utf-8", errors="replace")

    @tool
    def write_file(relative_path: str, content: str) -> str:
        """Write or overwrite a file. Parent directories are created automatically."""
        f = _under_workspace(relative_path, root)
        if isinstance(f, str):
            return f
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {relative_path!r}."

    @tool
    def edit_file(relative_path: str, old_str: str, new_str: str) -> str:
        """Replace exactly one occurrence of old_str in the file. old_str must be unique."""
        f = _under_workspace(relative_path, root)
        if isinstance(f, str):
            return f
        if not f.is_file():
            return f"Error: not a file: {relative_path!r}"
        text = f.read_text(encoding="utf-8", errors="replace")
        c = text.count(old_str)
        if c == 0:
            return "Error: old_str not found."
        if c > 1:
            return f"Error: old_str is not unique ({c} matches)."
        f.write_text(text.replace(old_str, new_str, 1), encoding="utf-8")
        return f"Replaced 1 occurrence in {relative_path!r}."

    @tool
    def list_dir(relative_path: str = "") -> str:
        """List files and subdirectories. Empty string = project root."""
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
        Run `go build ./...` from the project output root. Other packages may still be incomplete
        in early batches; focus on errors pointing at your assigned file. Success means exit code 0.
        """
        _ = target_rel  # kept for tool description / future per-file log filtering
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
        err_out = (p.stdout or "") + (p.stderr or "")
        if p.returncode == 0:
            return "OK: go build ./... succeeded.\n" + (err_out.strip() or "")
        return (
            f"FAILED: go build ./... exit {p.returncode}.\n"
            f"(Assigned file: {target_rel})\n{err_out[:12_000]}"
        )

    @tool
    def record_learning(topic: str, content: str) -> str:
        """Store a long-term project learning (e.g. Java/Go idiom) for later runs."""
        return record_learning(topic, content)

    @tool
    def search_learnings(query: str) -> str:
        """Search past learnings by keyword."""
        return search_learnings(query)

    @tool
    def load_skill_tool(skill_name: str) -> str:
        """Load a SKILL.md SOP from the skills/ directory."""
        return load_skill(skill_name)

    @tool
    def list_available_skills() -> str:
        """List skills with SKILL.md under the repository skills/ tree."""
        return list_skills()

    @tool
    def mcp_query(tool_name: str, arguments_json: str) -> str:
        """
        Call a configured stdio MCP server tool. Requires: pip install mcp and MIGRATION_MCP_COMMAND.
        arguments_json is a JSON object, e.g. {} or {"url": "https://..."}.
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


def read_output_go_text(workspace: Path) -> str:
    p = workspace / OUTPUT_FILE
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def _is_test_go_path(rel: str) -> bool:
    r = (rel or "").replace("\\", "/").strip()
    return r.endswith("_test.go") and not r.startswith("..")


def build_module_translate_tools(
    go_output_dir: Path,
    module_targets: list[tuple[str, str, str]],
) -> list:
    """
    Multi-file module migration: like build_project_file_tools, plus list_module_files
    and run_go_build refers to the whole module. module_targets: (java_rel, go_rel, go_package).
    """
    root = go_output_dir.resolve()
    if not root.is_dir():
        root.mkdir(parents=True, exist_ok=True)
    primary = (
        _rel_norm((module_targets[0][1] or "main.go").replace("\\", "/"))
        if module_targets
        else "main.go"
    )

    @tool
    def list_module_files() -> str:
        """List all Java->Go file assignments in this module (relative paths, package names)."""
        lines: list[str] = []
        for jr, gr, gpkg in module_targets:
            lines.append(
                f"- {jr!r}  ->  {gr!r}  (Go package: {gpkg!r})"
            )
        return "\n".join(lines) if lines else "(empty module)"

    @tool
    def read_file(relative_path: str) -> str:
        """Read a file under the project output directory. Use forward slashes, e.g. 'pkg/a.go'."""
        f = _under_workspace(relative_path, root)
        if isinstance(f, str):
            return f
        if not f.is_file():
            return f"Error: not a file: {relative_path!r}"
        return f.read_text(encoding="utf-8", errors="replace")

    @tool
    def write_file(relative_path: str, content: str) -> str:
        """Write or overwrite a file. Parent directories are created automatically."""
        f = _under_workspace(relative_path, root)
        if isinstance(f, str):
            return f
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {relative_path!r}."

    @tool
    def edit_file(relative_path: str, old_str: str, new_str: str) -> str:
        """Replace exactly one occurrence of old_str in the file. old_str must be unique."""
        f = _under_workspace(relative_path, root)
        if isinstance(f, str):
            return f
        if not f.is_file():
            return f"Error: not a file: {relative_path!r}"
        text = f.read_text(encoding="utf-8", errors="replace")
        c = text.count(old_str)
        if c == 0:
            return "Error: old_str not found."
        if c > 1:
            return f"Error: old_str is not unique ({c} matches)."
        f.write_text(text.replace(old_str, new_str, 1), encoding="utf-8")
        return f"Replaced 1 occurrence in {relative_path!r}."

    @tool
    def list_dir(relative_path: str = "") -> str:
        """List files and subdirectories. Empty string = project root."""
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
        Run `go build ./...` from the project output root. Success means exit code 0.
        """
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
        err_out = (p.stdout or "") + (p.stderr or "")
        if p.returncode == 0:
            return "OK: go build ./... succeeded.\n" + (err_out.strip() or "")
        return (
            f"FAILED: go build ./... exit {p.returncode}.\n"
            f"(Module primary: {primary})\n{err_out[:12_000]}"
        )

    @tool
    def record_learning(topic: str, content: str) -> str:
        """Store a long-term project learning (e.g. Java/Go idiom) for later runs."""
        return record_learning(topic, content)

    @tool
    def search_learnings(query: str) -> str:
        """Search past learnings by keyword."""
        return search_learnings(query)

    @tool
    def load_skill_tool(skill_name: str) -> str:
        """Load a SKILL.md SOP from the skills/ directory."""
        return load_skill(skill_name)

    @tool
    def list_available_skills() -> str:
        """List skills with SKILL.md under the repository skills/ tree."""
        return list_skills()

    @tool
    def mcp_query(tool_name: str, arguments_json: str) -> str:
        """
        Call a configured stdio MCP server tool. Requires: pip install mcp and MIGRATION_MCP_COMMAND.
        arguments_json is a JSON object, e.g. {} or {"url": "https://..."}.
        """
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
        list_dir,
        run_go_build,
        record_learning,
        search_learnings,
        load_skill_tool,
        list_available_skills,
        mcp_query,
        mcp_status,
    ]


def build_test_gen_tools(go_output_dir: Path) -> list:
    """
    Test-Gen agent: may only create/edit *_test.go; runs `go test ./...` to verify.
    No read of non-test Go sources to keep tests spec-driven from Java.
    """
    root = go_output_dir.resolve()
    if not root.is_dir():
        root.mkdir(parents=True, exist_ok=True)

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
        c = text.count(old_str)
        if c == 0:
            return "Error: old_str not found."
        if c > 1:
            return f"Error: old_str is not unique ({c} matches)."
        f.write_text(text.replace(old_str, new_str, 1), encoding="utf-8")
        return f"Replaced 1 occurrence in {relative_path!r}."

    @tool
    def run_go_tests_only() -> str:
        """Run `go test -count=1 ./...` from the project output root. Use after writing tests."""
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
        """Store a long-term project learning (e.g. Java/Go idiom) for later runs."""
        return record_learning(topic, content)

    @tool
    def search_learnings(query: str) -> str:
        """Search past learnings by keyword."""
        return search_learnings(query)

    return [
        write_test_file,
        edit_test_file,
        run_go_tests_only,
        record_learning,
        search_learnings,
    ]
