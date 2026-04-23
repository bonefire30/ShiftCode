"""
Filesystem + Go tooling helpers for multi-file project migration.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from symbol_table import SymbolTable


def _under_root(p: Path, root: Path) -> Path:
    p = p.resolve()
    r = root.resolve()
    if not str(p).startswith(str(r)):
        raise ValueError("path outside project")
    return p


def scan_java_project(project_dir: Path) -> list[str]:
    """List all .java paths relative to project_dir (posix)."""
    project_dir = project_dir.resolve()
    if not project_dir.is_dir():
        return []
    out: list[str] = []
    for f in sorted(project_dir.rglob("*.java")):
        try:
            rel = f.relative_to(project_dir)
        except ValueError:
            continue
        out.append(str(rel).replace("\\", "/"))
    return out


def read_java_file(project_dir: Path, relative_path: str) -> str:
    root = project_dir.resolve()
    rel = re.sub(r"\.{2,}", "", relative_path).lstrip("/\\")
    p = _under_root(root / rel, root)
    if not p.is_file():
        return f"Error: not a file: {relative_path!r}"
    return p.read_text(encoding="utf-8", errors="replace")


def write_go_file(output_dir: Path, relative_path: str, content: str) -> str:
    """
    Write Go source under output_dir, creating parents.
    relative_path like 'pkg/user/service.go' (forward slashes).
    """
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rel = re.sub(r"\.{2,}", "", relative_path or "").lstrip("/\\")
    if not rel.lower().endswith(".go"):
        rel += ".go"
    p = _under_root(output_dir / rel, output_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {rel!r}."


def init_go_module(output_dir: Path, module: str) -> str:
    """go mod init if go.mod missing."""
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    mod = output_dir / "go.mod"
    if mod.is_file():
        return f"go.mod already exists at {mod}"
    r = _run(["go", "mod", "init", module], cwd=str(output_dir))
    return r if r else f"Initialized {mod}"


def _run(cmd: list[str], cwd: str | None = None) -> str:
    try:
        p = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except FileNotFoundError as e:
        return f"Error: {e}\n(ensure {cmd[0]!r} is on PATH)"
    except subprocess.TimeoutExpired:
        return "Error: command timed out"
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        return f"exit {p.returncode}\n{out}"
    return out or ""


def go_build_status(output_dir: Path) -> tuple[bool, str]:
    """(ok, combined_output). ok True iff returncode==0."""
    output_dir = output_dir.resolve()
    if not output_dir.is_dir():
        return False, f"Error: not a directory: {output_dir}"
    try:
        p = subprocess.run(
            ["go", "build", "./..."],
            cwd=str(output_dir),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except FileNotFoundError as e:
        return False, str(e)
    except subprocess.TimeoutExpired:
        return False, "Error: go build timed out"
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode == 0, out or ""


def go_test_status(output_dir: Path) -> tuple[bool, str]:
    """(ok, combined_output). ok True iff `go test ./...` exit code is 0."""
    output_dir = output_dir.resolve()
    if not output_dir.is_dir():
        return False, f"Error: not a directory: {output_dir}"
    try:
        p = subprocess.run(
            ["go", "test", "-count=1", "./..."],
            cwd=str(output_dir),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except FileNotFoundError as e:
        return False, str(e)
    except subprocess.TimeoutExpired:
        return False, "Error: go test timed out"
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode == 0, out or ""


def run_go_build_package(output_dir: Path) -> str:
    ok, t = go_build_status(output_dir)
    return t if t else "OK" if ok else f"build failed: {t}"


def run_go_test_package(output_dir: Path) -> str:
    return _go_run(output_dir, "test", ["./..."])


def _go_run(output_dir: Path, sub: str, extra: list[str]) -> str:
    output_dir = output_dir.resolve()
    if not output_dir.is_dir():
        return f"Error: not a directory: {output_dir}"
    args = ["go", sub, "-count=1", *extra] if sub == "test" else ["go", sub, *extra]
    return _run(args, cwd=str(output_dir)) or "OK (no output)"


def run_golangci_lint(output_dir: Path) -> str:
    output_dir = output_dir.resolve()
    r = _run(
        ["golangci-lint", "run", "./..."],
        cwd=str(output_dir),
    )
    if r.startswith("Error:") and "golangci-lint" in r:
        return "golangci-lint not installed; skipped. Install: https://golangci-lint.run"
    return r or "OK"


def query_symbol_table(st: SymbolTable, class_name: str) -> str:
    e = st.get(class_name)
    if not e:
        for k, v in st._by_fqn.items():  # noqa: SLF001
            if k.endswith(f".{class_name}") or k == class_name:
                e = v
                break
    if not e:
        return f"No symbol for {class_name!r}."
    return (
        f"{e.java_fqn}\n"
        f"package: {e.package}\n"
        f"signatures: {e.java_signatures!r}\n"
        f"go snippet: {e.go_code_snippet[:2000]!r}"
    )


def ensure_min_go_files_for_build(output_dir: Path) -> None:
    """If directory has no go files, create placeholder so build fails clearly."""
    output_dir = output_dir.resolve()
    if not any(output_dir.rglob("*.go")):
        p = output_dir / "main.go"
        p.write_text(
            'package main\nimport "fmt"\nfunc main() { fmt.Println("empty module") }\n',
            encoding="utf-8",
        )
