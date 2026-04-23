"""
workflow.py — LangGraph: Translator (legacy one-shot or tool-calling Agent) -> QA (go build+test) with repair loop.
Optional: MemorySaver, reflection -> learnings.json.

Set MIGRATION_USE_AGENT=0 for legacy one-shot (full output in one block).
Set MIGRATION_USE_AGENT=1 (default) for file-tool agent with run_go_tests in-loop.

Requires: OPENAI_API_KEY, `go` on PATH.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

# --- env
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: S110
    pass

from evaluate import GoToolchainError, evaluate_case
from learnings import record_learning, search_learnings
from agent_tools import (
    OUTPUT_FILE,
    build_migration_tools,
    build_module_translate_tools,
    build_project_file_tools,
    build_test_gen_tools,
    read_output_go_text,
)

# LangGraph
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

try:
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover
    ChatOpenAI = None  # type: ignore[misc, assignment]

try:
    from langchain_core.messages import HumanMessage as _HM
except ImportError:  # pragma: no cover
    _HM = None  # type: ignore[misc, assignment]

DEFAULT_MAX_TRANSLATOR_CALLS = 3
DEFAULT_AGENT_STEPS = 35


def extract_go_code(llm_text: str) -> str:
    """Pull code from a markdown ```go``` fence or the whole string."""
    t = llm_text.strip()
    m = re.search(r"```(?:go|golang)?\s*([\s\S]*?)```", t, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return t


def load_stub_go(case_dir: Path) -> str:
    p = case_dir / "golden_output.go"
    if not p.is_file():
        raise FileNotFoundError(f"stub needs {p}")
    return p.read_text(encoding="utf-8")


class MigrationState(TypedDict, total=False):
    java_source: str
    case_dir: str
    go_code: str
    """Final migrated Go; read from workspace/output.go after agent or from legacy one-shot."""
    workspace_dir: str
    """Ephemeral work directory for the agent; optional cleanup after run."""
    messages: list[dict[str, Any]]
    """JSON-serializable message history (system/user/assistant/tool)."""
    last_repair_error: str
    compile_ok: bool
    test_ok: bool
    build_log: str
    test_log: str
    translator_calls: int
    max_translator_calls: int
    last_eval: dict[str, Any]
    total_tokens: int
    use_stub: bool
    qa_fatal: bool
    use_legacy_translator: bool
    """If True, one-shot code block (no file tools)."""
    reflect_ok: bool
    """Set after a successful `reflect` node."""


def _build_translator(*, streaming: bool = True) -> Any:
    if ChatOpenAI is None:
        raise RuntimeError("Install langchain-openai: pip install -r requirements.txt")
    kwargs: dict[str, Any] = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "temperature": 0.1,
        "streaming": streaming,
    }
    if os.environ.get("OPENAI_BASE_URL"):
        kwargs["base_url"] = os.environ["OPENAI_BASE_URL"]
    if os.environ.get("OPENAI_API_KEY"):
        kwargs["api_key"] = os.environ["OPENAI_API_KEY"]
    return ChatOpenAI(**kwargs)


SYSTEM_PROMPT = """You are an expert at migrating Java to idiomatic Go.
Output exactly one file: package `userservice` with all necessary imports (e.g., "errors", "fmt").
Requirements:
- `func NewUserService(dbConnection string) (*UserService, error)` — reject empty connection (error non-nil).
- `func (s *UserService) DBConnection() string`
- `func (s *UserService) GetUserStatus(age int) (string, error)` — negative age must return a non-nil error; strings "Adult" (age>=18) or "Minor" (else).
Respond with ONLY a ```go``` fenced code block, no other text."""


def load_system_prompt(case_dir: Path) -> str:
    """Per-benchmark `migration_prompt.txt` overrides the default UserService prompt."""
    p = case_dir / "migration_prompt.txt"
    if p.is_file():
        return p.read_text(encoding="utf-8").strip()
    return SYSTEM_PROMPT


def _new_workspace() -> Path:
    base = Path("run_workspaces")
    base.mkdir(exist_ok=True)
    w = base / f"ws_{uuid.uuid4().hex}"
    w.mkdir(parents=True, exist_ok=True)
    return w


def _tool_call_parts(tc: Any) -> tuple[str, dict[str, Any], str]:
    if isinstance(tc, dict):
        name = str(tc.get("name") or "")
        tid = str(tc.get("id") or "")
        args = tc.get("args")
        if args is None and isinstance(tc.get("function"), dict):
            raws = tc["function"].get("arguments") or "{}"
            try:
                args = json.loads(raws) if isinstance(raws, str) else (raws or {})
            except json.JSONDecodeError:
                args = {}
        if not isinstance(args, dict):
            args = {}
        return name, args, tid
    name = str(getattr(tc, "name", "") or "")
    args = getattr(tc, "args", None)
    if not isinstance(args, dict):
        args = {}
    tid = str(getattr(tc, "id", "") or "")
    return name, args, tid


def _add_tokens_from_response(resp: Any, total: int) -> int:
    meta = cast(dict[str, Any], getattr(resp, "response_metadata", None) or {})
    u = cast(Any, meta.get("token_usage") or meta.get("usage") or {})
    if isinstance(u, dict) and u:
        pr = u.get("prompt_tokens") or u.get("input_tokens")
        comp = u.get("completion_tokens") or u.get("output_tokens")
        if isinstance(pr, int) and isinstance(comp, int):
            return total + pr + comp
    return total


def messages_to_dicts(msgs: list) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in msgs:
        if isinstance(m, SystemMessage):
            out.append({"role": "system", "content": m.content or ""})
        elif isinstance(m, HumanMessage):
            out.append({"role": "user", "content": m.content or ""})
        elif isinstance(m, AIMessage):
            d: dict[str, Any] = {
                "role": "assistant",
                "content": m.content or "",
            }
            if m.tool_calls:
                d["tool_calls"] = m.tool_calls
            out.append(d)
        elif isinstance(m, ToolMessage):
            row: dict[str, Any] = {
                "role": "tool",
                "content": m.content,
                "tool_call_id": m.tool_call_id,
            }
            tn = getattr(m, "name", None)
            if tn:
                row["name"] = tn
            out.append(row)
    return out


def _emit_agent_intermediate(
    base: MigrationState,
    config: RunnableConfig | dict[str, Any] | None,
    *,
    workspace: Path,
    case_dir: Path,
    java: str,
    messages: list,
    n: int,
    total: int,
) -> None:
    """Notify StreamingCallback.on_agent_intermediate (SSE) during the agent tool loop."""
    if config is None:
        return
    if isinstance(config, dict):
        cbs = config.get("callbacks")
    else:
        cbs = getattr(config, "callbacks", None)
    if not cbs:
        return
    handlers = cbs if isinstance(cbs, list) else [cbs]
    partial: dict[str, Any] = {
        **base,
        "case_dir": str(case_dir),
        "java_source": java,
        "workspace_dir": str(workspace),
        "go_code": read_output_go_text(workspace),
        "messages": messages_to_dicts(messages),
        "translator_calls": n,
        "total_tokens": total,
    }
    for h in handlers:
        fn = getattr(h, "on_agent_intermediate", None)
        if callable(fn):
            fn(partial)
            break


def _use_agent_mode(state: MigrationState) -> bool:
    if state.get("use_stub") or os.environ.get("MIGRATION_USE_STUB") == "1":
        return False
    if state.get("use_legacy_translator"):
        return False
    return os.environ.get("MIGRATION_USE_AGENT", "1") != "0"


def _legacy_translator_node(
    state: MigrationState, config: RunnableConfig | None = None
) -> MigrationState:
    case_dir = Path(state["case_dir"])
    java = state["java_source"]
    err_hint = (state.get("last_repair_error") or "").strip()
    n = int(state.get("translator_calls") or 0) + 1
    if ChatOpenAI is None or _HM is None:
        raise RuntimeError("Install langchain-openai: pip install -r requirements.txt")
    llm = _build_translator(streaming=True)
    user = f"Java source:\n```java\n{java}\n```\n"
    if err_hint:
        user += (
            "\nPrevious build/test failed. Fix the Go code.\n```\n"
            f"{err_hint}\n```\n"
        )
    system = load_system_prompt(case_dir)
    resp = cast(Any, llm).invoke(
        [_HM(content=system + "\n\n" + user)],
        config=config,
    )
    text = resp.content if hasattr(resp, "content") else str(resp)
    if isinstance(text, list):
        text = "".join(str(p) for p in text)
    go_code = extract_go_code(str(text))
    total = int(state.get("total_tokens") or 0)
    total = _add_tokens_from_response(resp, total)
    return {
        **state,
        "go_code": go_code,
        "translator_calls": n,
        "total_tokens": total,
    }


def _agent_translator_node(
    state: MigrationState, config: RunnableConfig | None = None
) -> MigrationState:
    case_dir = Path(state["case_dir"])
    java = state["java_source"]
    err_hint = (state.get("last_repair_error") or "").strip()
    n = int(state.get("translator_calls") or 0) + 1
    if ChatOpenAI is None:
        raise RuntimeError("Install langchain-openai: pip install -r requirements.txt")

    ws_raw = (state.get("workspace_dir") or "").strip()
    if ws_raw and Path(ws_raw).is_dir():
        workspace = Path(ws_raw)
    else:
        workspace = _new_workspace()
    case_dir = case_dir.resolve()
    workspace = workspace.resolve()

    tools = build_migration_tools(workspace, case_dir)
    by_name: dict[str, Any] = {t.name: t for t in tools}  # type: ignore[attr-defined]
    llm = _build_translator(streaming=False)
    bound = cast(Any, llm).bind_tools(tools, parallel_tool_calls=True)

    system = load_system_prompt(case_dir)
    hints = search_learnings("java go", limit=2)
    if not hints.lower().startswith("no learnings") and len(hints) < 2000:
        system += f"\n\n### Past project learnings (search_learnings is also available as a tool)\n{hints}\n"
    system += (
        f"\n\n### Workspace (absolute): {workspace}\n"
        f"Write the migrated code to the file `{OUTPUT_FILE}` in this workspace. "
        "You may also read it with the read_file tool. "
        "Call run_go_tests after each substantive edit until it returns success."
    )
    err_block = (
        f"\n\n## Previous build/test error (repair round)\n```\n{err_hint}\n```\n"
        if err_hint
        else ""
    )
    user_block = (
        f"## Java to migrate\n```java\n{java}\n```\n{err_block}\n"
        "Create or fix `output.go` using the tools, then run run_go_tests until it reports OK."
    )
    messages: list = [
        SystemMessage(content=system),
        HumanMessage(content=user_block),
    ]
    max_steps = int(
        os.environ.get("MIGRATION_AGENT_STEPS", str(DEFAULT_AGENT_STEPS))
    )
    if max_steps < 1:
        max_steps = DEFAULT_AGENT_STEPS
    total = int(state.get("total_tokens") or 0)
    tests_passed = False
    for _step in range(max_steps):
        resp = cast(AIMessage, bound.invoke(messages, config=config))
        total = _add_tokens_from_response(resp, total)
        tca = list(resp.tool_calls or [])
        if not tca:
            if resp.content:
                messages.append(resp)
            if tests_passed:
                break
            messages.append(
                HumanMessage(
                    "Call run_go_tests to verify `output.go`, or use write_file/read_file/edit_file to fix it."
                )
            )
            _emit_agent_intermediate(
                state, config, workspace=workspace, case_dir=case_dir, java=java, messages=messages, n=n, total=total
            )
            continue
        messages.append(resp)
        _emit_agent_intermediate(
            state, config, workspace=workspace, case_dir=case_dir, java=java, messages=messages, n=n, total=total
        )
        for tc in tca:
            name, args, tid = _tool_call_parts(tc)
            tool = by_name.get(name)
            if not tool:
                out = f"Error: unknown tool {name!r}."
            else:
                out = str(tool.invoke(args))
            if name == "run_go_tests" and "OK: all tests passed" in out:
                tests_passed = True
            messages.append(
                ToolMessage(content=out, tool_call_id=tid, name=name)
            )
            _emit_agent_intermediate(
                state, config, workspace=workspace, case_dir=case_dir, java=java, messages=messages, n=n, total=total
            )
        if tests_passed:
            break

    go_code = read_output_go_text(workspace)
    if not go_code and tests_passed:
        go_code = (workspace / OUTPUT_FILE).read_text(encoding="utf-8", errors="replace")

    return {
        **state,
        "go_code": go_code,
        "workspace_dir": str(workspace),
        "messages": messages_to_dicts(messages),
        "translator_calls": n,
        "total_tokens": total,
    }


def run_file_agent(
    *,
    java_source: str,
    target_go_file: Path,
    go_output_dir: Path,
    context_hint: str = "",
    go_package: str = "main",
    err_hint: str = "",
    system_prompt_override: str = "",
    max_steps: int = DEFAULT_AGENT_STEPS,
    config: RunnableConfig | None = None,
) -> tuple[str, int, bool]:
    """
    Single-file worker: tools bind to the Go project output dir; writes `target_go_file`
    and runs `go build ./...` until build succeeds or step budget is exhausted.

    If ``system_prompt_override`` is set (e.g. project ``migration_prompt.txt``), it replaces
    the default role block in the system message.
    """
    if ChatOpenAI is None:
        raise RuntimeError("Install langchain-openai: pip install -r requirements.txt")

    go_out = go_output_dir.resolve()
    tgf = target_go_file.resolve()
    try:
        out_rel = tgf.relative_to(go_out).as_posix()
    except ValueError:
        out_rel = tgf.name

    tools = build_project_file_tools(go_out, out_rel)
    by_name: dict[str, Any] = {t.name: t for t in tools}  # type: ignore[attr-defined]
    llm = _build_translator(streaming=False)
    bound = cast(Any, llm).bind_tools(tools, parallel_tool_calls=True)

    default_role = (
        "You are an expert at migrating a single Java file to idiomatic Go inside a multi-file project."
    )
    role_block = (system_prompt_override or "").strip() or default_role
    lines = [
        role_block,
        f"**Assigned target file** — use write_file, read_file, and edit_file with this relative path: `{out_rel}`.",
        f"The first line of the file should be a valid `package` line (default package name if needed: `{go_package}`).",
        "Do not add a standalone `func main()` unless the migration spec explicitly requires an executable. "
        "Library packages must compile with `go build` / `go test` without an artificial entrypoint.",
        "Think first in <thought>...</thought> tags, then use tools. After substantive edits, call run_go_build. "
        "It runs `go build ./...` from the project root. Fix errors that reference this file; other packages may "
        "be incomplete in early translation batches and can be ignored for now as long as you cannot fix them here.",
    ]
    lhints = search_learnings("java go", limit=2)
    if not lhints.lower().startswith("no learnings") and len(lhints) < 2000:
        lines.append("### Learnings (search_learnings is also available as a tool)\n" + lhints)
    if context_hint.strip():
        lines.append("### Context from orchestrator\n" + context_hint.strip())
    system = "\n\n".join(lines)

    err_block = (
        f"\n## Previous / global build error context\n```\n{err_hint}\n```\n"
        if (err_hint or "").strip()
        else ""
    )
    user_block = (
        f"## Java source to migrate\n```java\n{java_source}\n```\n{err_block}\n"
        f"Create or update `{out_rel}` using the tools, then run run_go_build until it returns "
        f"`OK: go build ./... succeeded.`"
    )
    messages: list = [SystemMessage(content=system), HumanMessage(content=user_block)]
    steps = int(os.environ.get("MIGRATION_AGENT_STEPS", str(max_steps)))
    if steps < 1:
        steps = DEFAULT_AGENT_STEPS
    total = 0
    tests_passed = False
    for _ in range(steps):
        resp = cast(AIMessage, bound.invoke(messages, config=config))
        total = _add_tokens_from_response(resp, total)
        tca = list(resp.tool_calls or [])
        if not tca:
            if resp.content:
                messages.append(resp)
            if tests_passed:
                break
            messages.append(
                HumanMessage(
                    content=(
                        f"Call run_go_build, or use write_file / edit_file to update `{out_rel}`."
                    )
                )
            )
            continue
        messages.append(resp)
        for tc in tca:
            name, args, tid = _tool_call_parts(tc)
            tool = by_name.get(name)
            if not tool:
                out = f"Error: unknown tool {name!r}."
            else:
                out = str(tool.invoke(args))
            if name == "run_go_build" and "OK: go build ./... succeeded" in out:
                tests_passed = True
            messages.append(ToolMessage(content=out, tool_call_id=tid, name=name))
        if tests_passed:
            break

    tpath = go_out / out_rel
    go_code = ""
    if tpath.is_file():
        go_code = tpath.read_text(encoding="utf-8", errors="replace")
    if go_code.strip() and "package " not in go_code:
        go_code = f"package {go_package}\n\n" + go_code
    return go_code, total, tests_passed


def _java_to_go_relpath(java_rel: str) -> str:
    p = (java_rel or "").replace("\\", "/")
    if p.endswith(".java"):
        p = p[:-5]
    parts = p.split("/")
    if not parts:
        return "main.go"
    name = parts[-1]
    s1 = re.sub(r"(?<!^)(?=[A-Z])", "_", name)
    s1 = s1.lower().strip("_")
    if not s1:
        s1 = "type"
    if len(parts) == 1:
        return s1 + ".go"
    return "/".join(parts[:-1] + [s1 + ".go"])


def _go_to_test_relpath(go_rel: str) -> str:
    g = (go_rel or "").replace("\\", "/")
    if g.endswith(".go"):
        return g[: -len(".go")] + "_test.go"
    return g + "_test.go"


def run_module_agent(
    *,
    module_dep_order: list[str],
    java_sources: dict[str, str],
    go_output_dir: Path,
    go_package_map: dict[str, str],
    module_name: str = "module",
    context_hint: str = "",
    err_hint: str = "",
    system_prompt_override: str = "",
    max_steps: int = DEFAULT_AGENT_STEPS,
    config: RunnableConfig | None = None,
) -> tuple[dict[str, str], int, bool]:
    """
    Translate an entire module (ordered Java files) in one ReAct thread; one run_go_build success
    ends the successful loop.
    """
    if ChatOpenAI is None:
        raise RuntimeError("Install langchain-openai: pip install -r requirements.txt")
    go_out = go_output_dir.resolve()
    module_targets: list[tuple[str, str, str]] = []
    for jr in module_dep_order:
        gr = _java_to_go_relpath(jr)
        pkg = (go_package_map or {}).get(jr) or "main"
        module_targets.append((jr, gr, pkg))

    tools = build_module_translate_tools(go_out, module_targets)
    by_name: dict[str, Any] = {t.name: t for t in tools}  # type: ignore[attr-defined]
    llm = _build_translator(streaming=False)
    bound = cast(Any, llm).bind_tools(tools, parallel_tool_calls=True)

    default_role = (
        "You are an expert at migrating a cohesive group of related Java files to idiomatic "
        f"Go (module: {module_name!r})."
    )
    role_block = (system_prompt_override or "").strip() or default_role
    file_lines: list[str] = []
    for i, (jr, gr, gpkg) in enumerate(module_targets, 1):
        file_lines.append(f"{i}. {jr} -> {gr!r}  (use package {gpkg!r} in that file)")

    lines = [
        role_block,
        "**This module** — translate every file below in the given order; use `list_module_files` "
        "if you need a reminder. Use `write_file` for each `go` path; then call `run_go_build` "
        "until `go build ./...` succeeds.",
        "Do not add `func main()` unless the spec requires an executable.",
        "### Target files in dependency order",
        "\n".join(file_lines),
    ]
    lhints = search_learnings("java go", limit=2)
    if not lhints.lower().startswith("no learnings") and len(lhints) < 2000:
        lines.append("### Learnings (search_learnings is also a tool)\n" + lhints)
    if (context_hint or "").strip():
        lines.append("### Context from orchestrator\n" + context_hint.strip())
    system = "\n\n".join(lines)

    err_block = (
        f"\n## Previous / global build error context\n```\n{err_hint}\n```\n"
        if (err_hint or "").strip()
        else ""
    )
    src_blocks: list[str] = []
    for jr in module_dep_order:
        src = (java_sources or {}).get(jr, "")
        src_blocks.append(f"### {jr}\n```java\n{src}\n```\n")
    user_block = "\n".join(src_blocks) + err_block
    user_block += (
        "\nWrite all `write_file` targets, then use `run_go_build` until you see "
        "`OK: go build ./... succeeded.`"
    )
    messages: list = [SystemMessage(content=system), HumanMessage(content=user_block)]
    steps = int(os.environ.get("MIGRATION_AGENT_STEPS", str(max_steps)))
    if steps < 1:
        steps = DEFAULT_AGENT_STEPS
    total = 0
    build_ok = False
    for _ in range(steps):
        resp = cast(AIMessage, bound.invoke(messages, config=config))
        total = _add_tokens_from_response(resp, total)
        tca = list(resp.tool_calls or [])
        if not tca:
            if resp.content:
                messages.append(resp)
            if build_ok:
                break
            messages.append(
                HumanMessage(
                    content="Call `run_go_build`, or `write_file` / `edit_file` to update targets."
                )
            )
            continue
        messages.append(resp)
        for tc in tca:
            name, args, tid = _tool_call_parts(tc)
            tool = by_name.get(name)
            if not tool:
                out = f"Error: unknown tool {name!r}."
            else:
                out = str(tool.invoke(args))
            if name == "run_go_build" and "OK: go build ./... succeeded" in out:
                build_ok = True
            messages.append(ToolMessage(content=out, tool_call_id=tid, name=name))
        if build_ok:
            break

    out_by_rel: dict[str, str] = {}
    for jr, gr, _ in module_targets:
        tpath = go_out / gr
        if tpath.is_file():
            out_by_rel[jr] = tpath.read_text(encoding="utf-8", errors="replace")
    return out_by_rel, total, build_ok


def run_test_gen_module_agent(
    *,
    module_dep_order: list[str],
    java_sources: dict[str, str],
    go_output_dir: Path,
    go_package_map: dict[str, str],
    module_name: str = "module",
    err_hint: str = "",
    max_steps: int = DEFAULT_AGENT_STEPS,
    config: RunnableConfig | None = None,
) -> tuple[dict[str, str], int, bool]:
    """
    For each file in the module, create a matching `*_test.go` from Java only (no .go source reads).
    """
    if ChatOpenAI is None:
        raise RuntimeError("Install langchain-openai: pip install -r requirements.txt")
    go_out = go_output_dir.resolve()

    test_targets: list[tuple[str, str, str]] = []  # java_rel, go_rel, test_rel
    for jr in module_dep_order:
        gr = _java_to_go_relpath(jr)
        tr = _go_to_test_relpath(gr)
        test_targets.append((jr, gr, tr))

    tools = build_test_gen_tools(go_out)
    by_name: dict[str, Any] = {t.name: t for t in tools}  # type: ignore[attr-defined]
    llm = _build_translator(streaming=False)
    bound = cast(Any, llm).bind_tools(tools, parallel_tool_calls=True)

    tlines = []
    for i, (jr, gr, tr) in enumerate(test_targets, 1):
        gpkg = (go_package_map or {}).get(jr) or "main"
        tlines.append(
            f"{i}. From Java {jr!r} -> test file {tr!r} (package must match implementation {gpkg!r} "
            f"in sibling {gr!r})"
        )
    system = "\n\n".join(
        [
            "You are a Go QA engineer. Infer API contracts and edge cases from the Java sources below.",
            f"Module: {module_name!r}.",
            "Write one `*_test.go` for each file listed, using `write_test_file` / `edit_test_file` only. "
            "You must NOT use read_file to load non-test .go source — tests are derived from Java semantics. ",
            "CRITICAL: The implementation Go files HAVE ALREADY BEEN WRITTEN by another developer and exist in the workspace. "
            "DO NOT attempt to write or implement the actual Go source code (e.g., source.go). "
            "YOUR ONLY JOB is to write the test files (e.g., source_test.go).",
            "When tests are written, run `run_go_tests_only` until you see `OK: all tests passed.`",
            "### Test targets (same package as the implementation files)",
            "\n".join(tlines),
        ]
    )
    err_block = (
        f"\n## Previous test failure (fix only tests)\n```\n{err_hint}\n```\n"
        if (err_hint or "").strip()
        else ""
    )
    src_blocks: list[str] = []
    for jr in module_dep_order:
        src = (java_sources or {}).get(jr, "")
        src_blocks.append(f"### {jr}\n```java\n{src}\n```\n")
    user_block = "\n".join(src_blocks) + err_block
    user_block += (
        "\nUse the tools; finish with `run_go_tests_only` until tests pass and output contains "
        "`OK: all tests passed.`"
    )
    messages: list = [SystemMessage(content=system), HumanMessage(content=user_block)]
    steps = int(os.environ.get("MIGRATION_AGENT_STEPS", str(max_steps)))
    if steps < 1:
        steps = DEFAULT_AGENT_STEPS
    total = 0
    test_ok = False
    for _ in range(steps):
        resp = cast(AIMessage, bound.invoke(messages, config=config))
        total = _add_tokens_from_response(resp, total)
        tca = list(resp.tool_calls or [])
        if not tca:
            if resp.content:
                messages.append(resp)
            if test_ok:
                break
            messages.append(
                HumanMessage(
                    content="Use `write_test_file` / `edit_test_file` then `run_go_tests_only` until OK."
                )
            )
            continue
        messages.append(resp)
        for tc in tca:
            name, args, tid = _tool_call_parts(tc)
            tool = by_name.get(name)
            if not tool:
                out = f"Error: unknown tool {name!r}."
            else:
                out = str(tool.invoke(args))
            if name == "run_go_tests_only" and "OK: all tests passed" in out:
                test_ok = True
            messages.append(ToolMessage(content=out, tool_call_id=tid, name=name))
        if test_ok:
            break

    out_tests: dict[str, str] = {}
    for jr, _gr, tr in test_targets:
        tp = go_out / tr
        if tp.is_file():
            out_tests[jr] = tp.read_text(encoding="utf-8", errors="replace")
    return out_tests, total, test_ok


def translator_node(
    state: MigrationState, config: RunnableConfig | None = None
) -> MigrationState:
    if state.get("use_stub") or os.environ.get("MIGRATION_USE_STUB") == "1":
        case_dir = Path(state["case_dir"])
        n = int(state.get("translator_calls") or 0) + 1
        return {
            **state,
            "go_code": load_stub_go(case_dir),
            "translator_calls": n,
            "total_tokens": int(state.get("total_tokens") or 0),
        }
    if _use_agent_mode(state):
        return _agent_translator_node(state, config)
    return _legacy_translator_node(state, config)


def qa_node(state: MigrationState) -> MigrationState:
    case_dir = Path(state["case_dir"])
    go_code = state.get("go_code") or ""
    repair_turns = max(0, int(state.get("translator_calls") or 0) - 1)
    try:
        result = evaluate_case(
            case_dir,
            go_code,
            repair_turns=repair_turns,
            token_usage=int(state.get("total_tokens") or 0) or None,
            run_lint=False,
        )
    except FileNotFoundError as e:
        return {
            **state,
            "compile_ok": False,
            "test_ok": False,
            "build_log": str(e),
            "test_log": "",
            "last_repair_error": str(e),
            "last_eval": {},
        }
    except GoToolchainError as e:
        msg = str(e)
        return {
            **state,
            "compile_ok": False,
            "test_ok": False,
            "build_log": msg,
            "test_log": "",
            "last_repair_error": msg,
            "last_eval": {},
            "qa_fatal": True,
        }

    combined_err = "\n".join(
        x
        for x in [result.build_stderr, result.test_stderr, result.test_stdout]
        if (x and x.strip())
    )
    last_eval: dict[str, Any] = result.to_json()

    return {
        **state,
        "compile_ok": result.compile_ok,
        "test_ok": result.test_ok,
        "build_log": result.build_stderr,
        "test_log": (result.test_stderr or result.test_stdout or ""),
        "last_repair_error": combined_err
        if not (result.compile_ok and result.test_ok)
        else "",
        "last_eval": last_eval,
    }


def reflect_node(state: MigrationState) -> MigrationState:
    """Optional long-term write on success (lightweight, no extra LLM)."""
    if not state.get("test_ok") or state.get("use_stub"):
        return state
    case_name = Path(state.get("case_dir", "unknown") or "unknown").name
    try:
        record_learning(
            f"pass/{case_name}",
            f"Migration succeeded; calls={state.get('translator_calls')}, tokens={state.get('total_tokens')}.",
        )
    except OSError as e:  # pragma: no cover
        return {**state, "last_eval": {**(state.get("last_eval") or {}), "reflect_error": str(e)}}
    return {**state, "reflect_ok": True}


def route_after_qa(
    state: MigrationState,
) -> Literal["translator", "reflect", "end"]:
    if state.get("qa_fatal"):
        return "end"
    if state.get("test_ok") and state.get("compile_ok"):
        return "reflect"
    if int(state.get("translator_calls") or 0) >= int(
        state.get("max_translator_calls") or DEFAULT_MAX_TRANSLATOR_CALLS
    ):
        return "end"
    return "translator"


def build_graph() -> Any:
    g = StateGraph(MigrationState)
    g.add_node("translator", translator_node)
    g.add_node("qa", qa_node)
    g.add_node("reflect", reflect_node)
    g.set_entry_point("translator")
    g.add_edge("translator", "qa")
    g.add_conditional_edges(
        "qa",
        route_after_qa,
        {
            "translator": "translator",
            "reflect": "reflect",
            "end": END,
        },
    )
    g.add_edge("reflect", END)
    return g.compile(checkpointer=MemorySaver())


def _truncate_state_for_log(state: MigrationState) -> dict[str, Any]:
    o: dict[str, Any] = {}
    for k, v in state.items():
        if k == "messages" and isinstance(v, list) and len(v) > 40:
            o[k] = v[-40:]
        else:
            o[k] = v
    return o


def save_run_log(state: MigrationState) -> None:
    log_dir = Path("run_logs")
    log_dir.mkdir(exist_ok=True)
    case_dir_path = Path(state.get("case_dir", "unknown"))
    case_name = case_dir_path.name if case_dir_path.name else "unknown"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_state = _truncate_state_for_log(state)
    safe: dict[str, Any] = {}
    for k, v in out_state.items():
        if isinstance(v, (str, int, float, bool, type(None), dict, list)):
            safe[k] = v
        else:
            safe[k] = str(v)
    log_path = log_dir / f"{ts}_{case_name}.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(safe, f, ensure_ascii=False, indent=2)
    print(f"Saved run log to {log_path}", file=sys.stderr)


def _clean_workspace_dir(state: MigrationState) -> None:
    if (os.environ.get("MIGRATION_KEEP_WORKSPACE") or "").lower() in (
        "1",
        "true",
        "yes",
    ):
        return
    w = (state.get("workspace_dir") or "").strip()
    p = Path(w) if w else None
    if p and p.is_dir() and "run_workspaces" in str(p):
        shutil.rmtree(p, ignore_errors=True)


def _run_config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def run_workflow(
    case_dir: Path,
    *,
    max_translator_calls: int = DEFAULT_MAX_TRANSLATOR_CALLS,
    use_stub: bool = False,
    use_legacy_translator: bool = False,
) -> MigrationState:
    java_path = case_dir / "source.java"
    if not java_path.is_file():
        raise FileNotFoundError(f"Missing {java_path}")
    java_source = java_path.read_text(encoding="utf-8")
    if os.environ.get("MIGRATION_USE_STUB") == "1":
        use_stub = True
    if (os.environ.get("MIGRATION_USE_LEGACY", "") or "").lower() in (
        "1",
        "true",
    ):
        use_legacy_translator = True
    if os.environ.get("MIGRATION_USE_AGENT", "1") == "0":
        use_legacy_translator = True

    initial: MigrationState = {
        "java_source": java_source,
        "case_dir": str(case_dir.resolve()),
        "translator_calls": 0,
        "max_translator_calls": max_translator_calls,
        "use_stub": use_stub,
        "use_legacy_translator": use_legacy_translator,
        "total_tokens": 0,
    }
    g = build_graph()
    thread_id = f"{case_dir.name}-{uuid.uuid4().hex}"
    final_state = cast(
        MigrationState, g.invoke(initial, config=_run_config(thread_id))
    )
    try:
        save_run_log(final_state)
    except Exception as e:  # noqa: BLE001
        print(f"Warning: Failed to save run log: {e}", file=sys.stderr)
    _clean_workspace_dir(final_state)
    return final_state


def stream_workflow(
    case_dir: Path,
    *,
    max_translator_calls: int = DEFAULT_MAX_TRANSLATOR_CALLS,
    use_stub: bool = False,
    use_legacy_translator: bool = False,
    callbacks: list[Any] | None = None,
):
    java_path = case_dir / "source.java"
    if not java_path.is_file():
        raise FileNotFoundError(f"Missing {java_path}")
    java_source = java_path.read_text(encoding="utf-8")
    if os.environ.get("MIGRATION_USE_STUB") == "1":
        use_stub = True
    if (os.environ.get("MIGRATION_USE_LEGACY", "") or "").lower() in (
        "1",
        "true",
    ):
        use_legacy_translator = True
    if os.environ.get("MIGRATION_USE_AGENT", "1") == "0":
        use_legacy_translator = True

    initial: MigrationState = {
        "java_source": java_source,
        "case_dir": str(case_dir.resolve()),
        "translator_calls": 0,
        "max_translator_calls": max_translator_calls,
        "use_stub": use_stub,
        "use_legacy_translator": use_legacy_translator,
        "total_tokens": 0,
    }
    g = build_graph()
    thread_id = f"{case_dir.name}-stream-{uuid.uuid4().hex}"
    cfg: dict[str, Any] = _run_config(thread_id)
    if callbacks:
        cfg["callbacks"] = callbacks
    last_state = initial
    for step in g.stream(initial, config=cfg):
        if not step:
            continue
        for node_id, out in step.items():
            last_state = cast(MigrationState, out)
            yield str(node_id), last_state
    try:
        save_run_log(last_state)
    except Exception as e:  # noqa: BLE001
        print(f"Warning: Failed to save stream log: {e}", file=sys.stderr)
    _clean_workspace_dir(last_state)


def main() -> int:
    ap = argparse.ArgumentParser(description="Java -> Go migration LangGraph workflow")
    ap.add_argument(
        "--case",
        type=Path,
        default=Path("benchmark_dataset/tier2_oop/01_user_service"),
    )
    ap.add_argument("--max-calls", type=int, default=DEFAULT_MAX_TRANSLATOR_CALLS)
    ap.add_argument(
        "--stub",
        action="store_true",
        help="Use golden_output.go, no LLM (or MIGRATION_USE_STUB=1)",
    )
    ap.add_argument(
        "--legacy",
        action="store_true",
        help="One-shot block translator; no file tools (or MIGRATION_USE_AGENT=0)",
    )
    args = ap.parse_args()
    case_dir = args.case.resolve()
    try:
        out = run_workflow(
            case_dir,
            max_translator_calls=args.max_calls,
            use_stub=args.stub,
            use_legacy_translator=args.legacy
            or (os.environ.get("MIGRATION_USE_AGENT", "1") == "0"),
        )
    except Exception as e:  # noqa: BLE001
        print(f"error: {e}", file=sys.stderr)
        return 1
    print("## workflow result", flush=True)
    for k, v in out.items():
        if k in ("go_code", "java_source"):
            print(f"- {k}: <{len(str(v))} chars>", flush=True)
        else:
            print(f"- {k}: {v!r}", flush=True)
    if out.get("test_ok") and out.get("compile_ok"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
