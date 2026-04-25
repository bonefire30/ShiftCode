"""
Shared project-migration agent helpers.

This module no longer exposes the retired single-case migration workflow.
It keeps only the reusable agent runners that are used by the multi-file
project migration graph.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: S110
    pass

from agent_tools import (
    build_module_translate_tools,
    build_project_file_tools,
    build_test_gen_tools,
)
from learnings import search_learnings
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from openai import BadRequestError, OpenAI

try:
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover
    ChatOpenAI = None  # type: ignore[misc, assignment]


DEFAULT_AGENT_STEPS = 35
DEFAULT_TRANSLATE_STEPS = 18
DEFAULT_TEST_GEN_STEPS = 16


def _is_deepseek_provider() -> bool:
    base_url = (os.environ.get("OPENAI_BASE_URL") or "").strip()
    if not base_url:
        return False
    try:
        parsed = urlparse(base_url)
    except Exception:  # noqa: BLE001
        return "api.deepseek.com" in base_url.lower()
    return "api.deepseek.com" in (parsed.netloc or parsed.path).lower()


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


def _build_deepseek_client() -> OpenAI:
    kwargs: dict[str, Any] = {}
    if os.environ.get("OPENAI_BASE_URL"):
        kwargs["base_url"] = os.environ["OPENAI_BASE_URL"]
    if os.environ.get("OPENAI_API_KEY"):
        kwargs["api_key"] = os.environ["OPENAI_API_KEY"]
    return OpenAI(**kwargs)


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
    usage = cast(Any, meta.get("token_usage") or meta.get("usage") or {})
    if isinstance(usage, dict) and usage:
        prompt = usage.get("prompt_tokens") or usage.get("input_tokens")
        completion = usage.get("completion_tokens") or usage.get("output_tokens")
        if isinstance(prompt, int) and isinstance(completion, int):
            return total + prompt + completion
    return total


def _add_tokens_from_openai_response(resp: Any, total: int) -> int:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return total
    prompt = getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None)
    completion = getattr(usage, "completion_tokens", None) or getattr(
        usage, "output_tokens", None
    )
    if isinstance(prompt, int) and isinstance(completion, int):
        return total + prompt + completion
    return total


def _tool_to_openai_spec(tool: Any) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": str(getattr(tool, "name", "")),
            "description": str(getattr(tool, "description", "") or ""),
            "parameters": {
                "type": "object",
                "properties": dict(getattr(tool, "args", {}) or {}),
            },
        },
    }


def _serialize_openai_tool_call(tc: Any) -> dict[str, Any]:
    function = getattr(tc, "function", None)
    name = str(getattr(function, "name", "") or "")
    arguments = getattr(function, "arguments", "{}")
    return {
        "id": str(getattr(tc, "id", "") or ""),
        "type": str(getattr(tc, "type", "function") or "function"),
        "function": {
            "name": name,
            "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments or {}),
        },
    }


def _assistant_message_from_openai(choice_message: Any) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "role": "assistant",
        "content": getattr(choice_message, "content", "") or "",
    }
    reasoning = _extract_reasoning_content(choice_message)
    if reasoning:
        msg["reasoning_content"] = reasoning
    tool_calls = list(getattr(choice_message, "tool_calls", None) or [])
    if tool_calls:
        msg["tool_calls"] = [_serialize_openai_tool_call(tc) for tc in tool_calls]
    return msg


def _extract_reasoning_content(choice_message: Any) -> str:
    reasoning = getattr(choice_message, "reasoning_content", None)
    if reasoning:
        return str(reasoning)
    extra = getattr(choice_message, "model_extra", None)
    if isinstance(extra, dict) and extra.get("reasoning_content"):
        return str(extra["reasoning_content"])
    dump_fn = getattr(choice_message, "model_dump", None)
    if callable(dump_fn):
        try:
            dumped = dump_fn()
        except Exception:  # noqa: BLE001
            dumped = {}
        if isinstance(dumped, dict) and dumped.get("reasoning_content"):
            return str(dumped["reasoning_content"])
    return ""


def _strip_reasoning_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stripped: list[dict[str, Any]] = []
    for message in messages:
        item = dict(message)
        item.pop("reasoning_content", None)
        stripped.append(item)
    return stripped


def _is_progress_tool(name: str) -> bool:
    return name in {
        "write_file",
        "edit_file",
        "write_test_file",
        "edit_test_file",
        "run_go_build",
        "run_go_tests_only",
    }


def _run_deepseek_tool_loop(
    *,
    system: str,
    user: str,
    tools: list[Any],
    success_predicate: Any,
    followup_user_prompt: str,
    max_steps: int,
    max_no_progress_steps: int = 5,
    enable_thinking: bool | None = None,
    config: RunnableConfig | None = None,
) -> tuple[int, bool]:
    del config
    client = _build_deepseek_client()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    tool_specs = [_tool_to_openai_spec(t) for t in tools]
    by_name: dict[str, Any] = {t.name: t for t in tools}  # type: ignore[attr-defined]
    total = 0
    success = False
    no_progress_steps = 0
    thinking_enabled = (
        str(os.environ.get("DEEPSEEK_THINKING", "0")).strip().lower() not in {"0", "false", "no", "off"}
        if enable_thinking is None
        else bool(enable_thinking)
    )
    for step_idx in range(1, max_steps + 1):
        request: dict[str, Any] = {
            "model": os.environ.get("OPENAI_MODEL", "deepseek-v4-flash"),
            "messages": messages,
            "tools": tool_specs,
            "parallel_tool_calls": True,
            "stream": False,
        }
        if thinking_enabled:
            request["reasoning_effort"] = "high"
            request["extra_body"] = {"thinking": {"type": "enabled"}}
        else:
            request["extra_body"] = {"thinking": {"type": "disabled"}}
        try:
            resp = client.chat.completions.create(**request)
        except BadRequestError as exc:
            if "reasoning_content" in str(exc):
                thinking_enabled = False
                fallback_request = dict(request)
                fallback_request.pop("reasoning_effort", None)
                fallback_request["extra_body"] = {"thinking": {"type": "disabled"}}
                fallback_request["messages"] = _strip_reasoning_messages(messages)
                try:
                    resp = client.chat.completions.create(**fallback_request)
                except BadRequestError:
                    break
            else:
                raise
        total = _add_tokens_from_openai_response(resp, total)
        choice = resp.choices[0]
        msg = choice.message
        assistant_msg = _assistant_message_from_openai(msg)
        tool_calls = list(getattr(msg, "tool_calls", None) or [])
        messages.append(assistant_msg)
        if not tool_calls:
            if success:
                break
            no_progress_steps += 1
            if no_progress_steps >= max_no_progress_steps:
                break
            messages.append({"role": "user", "content": followup_user_prompt})
            continue
        made_progress = False
        for tc in tool_calls:
            function = getattr(tc, "function", None)
            name = str(getattr(function, "name", "") or "")
            raw_args = getattr(function, "arguments", "{}")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            tool = by_name.get(name)
            try:
                out = f"Error: unknown tool {name!r}." if not tool else str(tool.invoke(args))
            except Exception as exc:  # noqa: BLE001
                out = f"Error running tool {name!r}: {exc}"
            if success_predicate(name, out):
                success = True
            if _is_progress_tool(name):
                made_progress = True
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(getattr(tc, "id", "") or ""),
                    "content": out,
                }
            )
        no_progress_steps = 0 if made_progress else no_progress_steps + 1
        if success:
            break
        if no_progress_steps >= max_no_progress_steps:
            break
    return total, success


def _java_to_go_relpath(java_rel: str) -> str:
    p = (java_rel or "").replace("\\", "/")
    if p.endswith(".java"):
        p = p[:-5]
    parts = p.split("/")
    if not parts:
        return "main.go"
    name = parts[-1]
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower().strip("_")
    if not snake:
        snake = "type"
    if len(parts) == 1:
        return snake + ".go"
    return "/".join(parts[:-1] + [snake + ".go"])


def _go_to_test_relpath(go_rel: str) -> str:
    g = (go_rel or "").replace("\\", "/")
    if g.endswith(".go"):
        return g[: -len(".go")] + "_test.go"
    return g + "_test.go"


def _norm_relpath(path: str) -> str:
    rel = (path or "").strip().replace("\\", "/").lstrip("/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def _snapshot_files(
    root: Path,
    *,
    include: Any,
) -> dict[str, str]:
    snap: dict[str, str] = {}
    if not root.is_dir():
        return snap
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = _norm_relpath(p.relative_to(root).as_posix())
        if not include(rel):
            continue
        try:
            data = p.read_bytes()
        except OSError:
            continue
        snap[rel] = hashlib.sha1(data).hexdigest()
    return snap


def _diff_snapshot_files(before: dict[str, str], after: dict[str, str]) -> list[str]:
    changed: list[str] = []
    for rel, digest in after.items():
        if before.get(rel) != digest:
            changed.append(rel)
    return sorted(changed)


def _extract_written_files_from_tool(by_name: dict[str, Any]) -> list[str]:
    tool = by_name.get("list_written_files")
    if not tool:
        return []
    try:
        raw = str(tool.invoke({}))
    except Exception:  # noqa: BLE001
        return []
    try:
        vals = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(vals, list):
        return []
    out: list[str] = []
    for v in vals:
        if isinstance(v, str):
            rel = _norm_relpath(v)
            if rel:
                out.append(rel)
    return sorted(set(out))


def _module_prefixes_from_paths(paths: list[str]) -> list[str]:
    prefixes: set[str] = set()
    for p in paths:
        rel = _norm_relpath(p)
        parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
        prefixes.add(parent)
    return sorted(prefixes)


def _in_prefixes(rel: str, prefixes: list[str]) -> bool:
    if not prefixes:
        return True
    for pref in prefixes:
        if not pref:
            return True
        if rel == pref or rel.startswith(pref + "/"):
            return True
    return False


def _expected_test_targets_from_go_files(go_files: list[str]) -> list[str]:
    return sorted(
        {
            _go_to_test_relpath(_norm_relpath(gr))
            for gr in go_files
            if _norm_relpath(gr).endswith(".go") and not _norm_relpath(gr).endswith("_test.go")
        }
    )


def _merge_effective_files(declared_files: list[str], diff_files: list[str]) -> list[str]:
    return sorted({_norm_relpath(p) for p in [*declared_files, *diff_files] if _norm_relpath(p)})


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
    Single-file project worker used inside project migration.
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

    default_role = (
        "You are an expert at migrating a single Java file to idiomatic Go inside a multi-file project."
    )
    role_block = (system_prompt_override or "").strip() or default_role
    lines = [
        role_block,
        f"Use write_file, read_file, and edit_file with the relative path `{out_rel}`.",
        f"The file should start with a valid package line (default package `{go_package}`).",
        "Do not add func main() unless the migration spec requires an executable.",
        "After substantive edits, call run_go_build and iterate until it succeeds.",
    ]
    learnings = search_learnings("java go", limit=2)
    if not learnings.lower().startswith("no learnings") and len(learnings) < 2000:
        lines.append("### Learnings\n" + learnings)
    if context_hint.strip():
        lines.append("### Context\n" + context_hint.strip())
    system = "\n\n".join(lines)

    err_block = (
        f"\n## Previous build error\n```\n{err_hint}\n```\n"
        if (err_hint or "").strip()
        else ""
    )
    user_block = (
        f"## Java source\n```java\n{java_source}\n```\n{err_block}\n"
        f"Create or update `{out_rel}` and run run_go_build until it returns "
        "`OK: go build ./... succeeded.`"
    )
    messages: list[Any] = [SystemMessage(content=system), HumanMessage(content=user_block)]
    default_steps = min(int(max_steps), DEFAULT_TRANSLATE_STEPS)
    steps = int(os.environ.get("MIGRATION_AGENT_STEPS", str(default_steps)))
    if steps < 1:
        steps = DEFAULT_AGENT_STEPS
    if _is_deepseek_provider():
        total, build_ok = _run_deepseek_tool_loop(
            system=system,
            user=user_block,
            tools=tools,
            success_predicate=lambda name, out: name == "run_go_build"
            and "OK: go build ./... succeeded" in out,
            followup_user_prompt=(
                f"Call run_go_build, or use write_file / edit_file to update `{out_rel}`."
            ),
            max_steps=steps,
            max_no_progress_steps=5,
            config=config,
        )
    else:
        llm = _build_translator(streaming=False)
        bound = cast(Any, llm).bind_tools(tools, parallel_tool_calls=True)
        total = 0
        build_ok = False
        for _ in range(steps):
            resp = cast(AIMessage, bound.invoke(messages, config=config))
            total = _add_tokens_from_response(resp, total)
            tool_calls = list(resp.tool_calls or [])
            if not tool_calls:
                if resp.content:
                    messages.append(resp)
                if build_ok:
                    break
                messages.append(
                    HumanMessage(
                        content=f"Call run_go_build, or use write_file / edit_file to update `{out_rel}`."
                    )
                )
                continue
            messages.append(resp)
            for tc in tool_calls:
                name, args, tid = _tool_call_parts(tc)
                tool = by_name.get(name)
                out = f"Error: unknown tool {name!r}." if not tool else str(tool.invoke(args))
                if name == "run_go_build" and "OK: go build ./... succeeded" in out:
                    build_ok = True
                messages.append(ToolMessage(content=out, tool_call_id=tid, name=name))
            if build_ok:
                break

    tpath = go_out / out_rel
    go_code = ""
    if tpath.is_file():
        go_code = tpath.read_text(encoding="utf-8", errors="replace")
    if go_code.strip() and "package " not in go_code:
        go_code = f"package {go_package}\n\n" + go_code
    return go_code, total, build_ok


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
) -> tuple[dict[str, str], int, bool, dict[str, Any]]:
    """
    Translate an entire module (ordered Java files) in one ReAct thread.
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
    expected_go_files = [_norm_relpath(gr) for _jr, gr, _pkg in module_targets]
    module_prefixes = _module_prefixes_from_paths(expected_go_files)
    before_snap = _snapshot_files(
        go_out,
        include=lambda rel: rel.endswith(".go")
        and not rel.endswith("_test.go")
        and _in_prefixes(rel, module_prefixes),
    )

    default_role = (
        "You are an expert at migrating a cohesive group of related Java files to idiomatic "
        f"Go (module: {module_name!r})."
    )
    role_block = (system_prompt_override or "").strip() or default_role
    file_lines = [
        f"{idx}. {jr} -> {gr!r} (use package {pkg!r} in that file)"
        for idx, (jr, gr, pkg) in enumerate(module_targets, 1)
    ]
    lines = [
        role_block,
        "Translate every file below in the given order and use list_module_files if needed.",
        "Write each Go file, then call run_go_build until go build ./... succeeds.",
        "Do not add func main() unless the spec requires an executable.",
        "### Target files",
        "\n".join(file_lines),
    ]
    learnings = search_learnings("java go", limit=2)
    if not learnings.lower().startswith("no learnings") and len(learnings) < 2000:
        lines.append("### Learnings\n" + learnings)
    if (context_hint or "").strip():
        lines.append("### Context from orchestrator\n" + context_hint.strip())
    system = "\n\n".join(lines)

    err_block = (
        f"\n## Previous / global build error\n```\n{err_hint}\n```\n"
        if (err_hint or "").strip()
        else ""
    )
    src_blocks = [f"### {jr}\n```java\n{(java_sources or {}).get(jr, '')}\n```\n" for jr in module_dep_order]
    user_block = "\n".join(src_blocks) + err_block
    user_block += (
        "\nWrite all targets, then use run_go_build until you see "
        "`OK: go build ./... succeeded.`"
    )
    messages: list[Any] = [SystemMessage(content=system), HumanMessage(content=user_block)]
    default_steps = min(int(max_steps), DEFAULT_TRANSLATE_STEPS)
    steps = int(os.environ.get("MIGRATION_AGENT_STEPS", str(default_steps)))
    if steps < 1:
        steps = DEFAULT_AGENT_STEPS
    if _is_deepseek_provider():
        total, build_ok = _run_deepseek_tool_loop(
            system=system,
            user=user_block,
            tools=tools,
            success_predicate=lambda name, out: name == "run_go_build"
            and "OK: go build ./... succeeded" in out,
            followup_user_prompt="Call run_go_build, or use write_file / edit_file to update targets.",
            max_steps=steps,
            max_no_progress_steps=6,
            config=config,
        )
    else:
        llm = _build_translator(streaming=False)
        bound = cast(Any, llm).bind_tools(tools, parallel_tool_calls=True)
        total = 0
        build_ok = False
        for _ in range(steps):
            resp = cast(AIMessage, bound.invoke(messages, config=config))
            total = _add_tokens_from_response(resp, total)
            tool_calls = list(resp.tool_calls or [])
            if not tool_calls:
                if resp.content:
                    messages.append(resp)
                if build_ok:
                    break
                messages.append(
                    HumanMessage(
                        content="Call run_go_build, or use write_file / edit_file to update targets."
                    )
                )
                continue
            messages.append(resp)
            for tc in tool_calls:
                name, args, tid = _tool_call_parts(tc)
                tool = by_name.get(name)
                out = f"Error: unknown tool {name!r}." if not tool else str(tool.invoke(args))
                if name == "run_go_build" and "OK: go build ./... succeeded" in out:
                    build_ok = True
                messages.append(ToolMessage(content=out, tool_call_id=tid, name=name))
            if build_ok:
                break

    declared_files = _extract_written_files_from_tool(by_name)
    declared_go_files = sorted(
        {
            rel
            for rel in declared_files
            if rel.endswith(".go")
            and not rel.endswith("_test.go")
            and _in_prefixes(rel, module_prefixes)
        }
    )
    after_snap = _snapshot_files(
        go_out,
        include=lambda rel: rel.endswith(".go")
        and not rel.endswith("_test.go")
        and _in_prefixes(rel, module_prefixes),
    )
    diff_go_files = _diff_snapshot_files(before_snap, after_snap)
    effective_go_files = _merge_effective_files(declared_go_files, diff_go_files)
    existing_expected_go_files = sorted(
        {gr for gr in expected_go_files if (go_out / gr).is_file()}
    )
    effective_go_files = _merge_effective_files(effective_go_files, existing_expected_go_files)
    missing_go_files = [gr for gr in expected_go_files if gr not in set(effective_go_files) and not (go_out / gr).is_file()]

    out_by_rel: dict[str, str] = {}
    for jr, gr, _ in module_targets:
        tpath = go_out / gr
        if tpath.is_file():
            out_by_rel[jr] = tpath.read_text(encoding="utf-8", errors="replace")
    artifacts = {
        "written_files": declared_go_files,
        "detected_new_or_changed_files": diff_go_files,
        "effective_output_files": effective_go_files,
        "declared_count": len(declared_go_files),
        "diff_count": len(diff_go_files),
        "effective_count": len(effective_go_files),
    }
    module_ok = build_ok and not missing_go_files
    return out_by_rel, total, module_ok, artifacts


def run_test_gen_module_agent(
    *,
    module_dep_order: list[str],
    java_sources: dict[str, str],
    go_output_dir: Path,
    go_package_map: dict[str, str],
    migration_prompt_text: str = "",
    prompt_contract_checklist: list[str] | None = None,
    expected_go_files: list[str] | None = None,
    module_name: str = "module",
    err_hint: str = "",
    max_steps: int = DEFAULT_AGENT_STEPS,
    config: RunnableConfig | None = None,
) -> tuple[dict[str, str], int, bool, int, int, list[str], dict[str, Any]]:
    """
    Create matching *_test.go files from Java semantics only.
    """
    if ChatOpenAI is None:
        raise RuntimeError("Install langchain-openai: pip install -r requirements.txt")
    go_out = go_output_dir.resolve()

    test_targets: list[tuple[str, str, str]] = []
    for jr in module_dep_order:
        gr = _java_to_go_relpath(jr)
        tr = _go_to_test_relpath(gr)
        test_targets.append((jr, gr, tr))
    expected_go_targets = sorted(
        {
            _norm_relpath(g)
            for g in (expected_go_files or [])
            if _norm_relpath(g).endswith(".go") and not _norm_relpath(g).endswith("_test.go")
        }
    )
    if not expected_go_targets:
        expected_go_targets = sorted({_norm_relpath(gr) for _jr, gr, _tr in test_targets})
    expected_test_targets = _expected_test_targets_from_go_files(expected_go_targets)
    module_prefixes = _module_prefixes_from_paths(expected_test_targets)

    tools = build_test_gen_tools(go_out)
    by_name: dict[str, Any] = {t.name: t for t in tools}  # type: ignore[attr-defined]
    before_snap = _snapshot_files(
        go_out,
        include=lambda rel: rel.endswith("_test.go") and _in_prefixes(rel, module_prefixes),
    )

    target_lines = []
    for idx, (jr, gr, tr) in enumerate(test_targets, 1):
        pkg = (go_package_map or {}).get(jr) or "main"
        target_lines.append(
            f"{idx}. From Java {jr!r} -> test file {tr!r} (package {pkg!r}, sibling {gr!r})"
        )
    checklist = [c.strip() for c in (prompt_contract_checklist or []) if c and c.strip()]
    checklist_block = "\n".join(f"- {item}" for item in checklist) if checklist else "- (none)"
    prompt_block = (migration_prompt_text or "").strip() or "(migration prompt missing)"

    system = "\n\n".join(
        [
            "You are a Go QA engineer. Infer ONLY the explicit API contracts from the Java sources, the migration prompt, and the generated Go files.",
            f"Module: {module_name!r}.",
            "First inspect the existing sibling Go source files with read_file so tests match the actual API names and package.",
            "Write one *_test.go per file using write_test_file / edit_test_file only.",
            "Do not implement the Go source files. They already exist in the workspace.",
            "Do not invent new runtime contracts. If Java, the migration prompt, and the generated Go API do not clearly require a behavior, do not assert it.",
            "Do not add tests for nil inputs, panic/recover behavior, concurrency, security, or exception paths unless they are explicitly required.",
            "Do not add expected-panic tests unless Java or the migration prompt explicitly requires a panic.",
            "Prioritize explicit migration-prompt requirements and observable Java behavior over extra edge cases.",
            "Every explicit contract named in the migration prompt must have a corresponding test.",
            "If the migration prompt requires delegation or call-order behavior, verify that behavior directly. Use a focused fake/spy when possible, or a narrow source-structure assertion against the generated Go file when the contract is otherwise not observable from outputs alone.",
            "Focus on return-value contracts, constructor and field visibility contracts, delegation contracts, and side-effect/call-order contracts.",
            "Only call run_go_tests_only after all expected test files have been written.",
            "When tests are written, run run_go_tests_only until it reports success.",
            "### Migration Prompt (verbatim)",
            prompt_block,
            "### Required Prompt Contracts Checklist",
            checklist_block,
            "### Test targets",
            "\n".join(target_lines),
        ]
    )
    err_block = (
        f"\n## Previous test failure (fix tests only)\n```\n{err_hint}\n```\n"
        if (err_hint or "").strip()
        else ""
    )
    src_blocks = [f"### {jr}\n```java\n{(java_sources or {}).get(jr, '')}\n```\n" for jr in module_dep_order]
    user_block = "\n".join(src_blocks) + err_block
    user_block += (
        "\nRead the sibling Go source for each target before writing tests."
        "\nYou must create every listed *_test.go file."
        "\nOnly assert behavior that is explicit in the Java source, migration prompt, or generated Go API."
        "\nDo not invent nil/panic/concurrency/error-path requirements unless they are explicitly required."
        "\nDo not write expected-panic or nil-input assertions unless the migration prompt, Java source, or Go API explicitly requires them."
        "\nIf the migration prompt names delegation or call-order behavior, add a test that verifies that exact contract instead of only checking final return values."
        "\nUse the checklist above as a must-cover list: every checklist item must appear in at least one assertion."
        "\nUse the tools and finish with run_go_tests_only until it returns "
        "`OK: all tests passed.`"
    )
    messages: list[Any] = [SystemMessage(content=system), HumanMessage(content=user_block)]
    default_steps = min(int(max_steps), DEFAULT_TEST_GEN_STEPS)
    steps = int(os.environ.get("MIGRATION_AGENT_STEPS", str(default_steps)))
    if steps < 1:
        steps = DEFAULT_AGENT_STEPS
    if _is_deepseek_provider():
        total, test_ok = _run_deepseek_tool_loop(
            system=system,
            user=user_block,
            tools=tools,
            success_predicate=lambda name, out: name == "run_go_tests_only"
            and "OK: all tests passed" in out,
            followup_user_prompt=(
                "Read the sibling Go source with read_file, write every expected *_test.go, "
                "cover every explicit migration-prompt contract without inventing nil/panic behavior, "
                "and then use run_go_tests_only until OK."
            ),
            max_steps=steps,
            max_no_progress_steps=4,
            enable_thinking=False,
            config=config,
        )
    else:
        llm = _build_translator(streaming=False)
        bound = cast(Any, llm).bind_tools(tools, parallel_tool_calls=True)
        total = 0
        test_ok = False
        for _ in range(steps):
            resp = cast(AIMessage, bound.invoke(messages, config=config))
            total = _add_tokens_from_response(resp, total)
            tool_calls = list(resp.tool_calls or [])
            if not tool_calls:
                if resp.content:
                    messages.append(resp)
                if test_ok:
                    break
                messages.append(
                    HumanMessage(
                        content=(
                            "Read the sibling Go source with read_file, write every expected "
                            "*_test.go via write_test_file / edit_test_file, cover every "
                            "explicit migration-prompt contract, avoid inventing nil/panic "
                            "behavior, and then use run_go_tests_only until OK."
                        )
                    )
                )
                continue
            messages.append(resp)
            for tc in tool_calls:
                name, args, tid = _tool_call_parts(tc)
                tool = by_name.get(name)
                out = f"Error: unknown tool {name!r}." if not tool else str(tool.invoke(args))
                if name == "run_go_tests_only" and "OK: all tests passed" in out:
                    test_ok = True
                messages.append(ToolMessage(content=out, tool_call_id=tid, name=name))
            if test_ok:
                break

    declared_files = _extract_written_files_from_tool(by_name)
    declared_test_files = sorted(
        {
            rel
            for rel in declared_files
            if rel.endswith("_test.go") and _in_prefixes(rel, module_prefixes)
        }
    )
    after_snap = _snapshot_files(
        go_out,
        include=lambda rel: rel.endswith("_test.go") and _in_prefixes(rel, module_prefixes),
    )
    diff_test_files = _diff_snapshot_files(before_snap, after_snap)
    effective_test_files = _merge_effective_files(declared_test_files, diff_test_files)
    existing_expected_test_files = sorted(
        {rel for rel in expected_test_targets if (go_out / rel).is_file()}
    )
    effective_test_files = _merge_effective_files(
        effective_test_files,
        existing_expected_test_files,
    )

    out_tests: dict[str, str] = {}
    for tr in effective_test_files:
        tp = go_out / tr
        if tp.is_file():
            out_tests[tr] = tp.read_text(encoding="utf-8", errors="replace")

    expected_count = len(expected_test_targets)
    generated_count = len(effective_test_files)
    failures: list[str] = []
    missing_targets = [tr for tr in expected_test_targets if tr not in set(effective_test_files)]
    if missing_targets:
        failures.append(
            f"module {module_name}: missing generated tests for {', '.join(sorted(missing_targets))}"
        )
    if not test_ok:
        failures.append(
            f"module {module_name}: run_go_tests_only did not reach `OK: all tests passed.`"
        )
    final_ok = test_ok and generated_count == expected_count
    artifacts = {
        "written_files": declared_test_files,
        "detected_new_or_changed_files": diff_test_files,
        "effective_output_files": effective_test_files,
        "expected_output_files": expected_test_targets,
        "declared_count": len(declared_test_files),
        "diff_count": len(diff_test_files),
        "effective_count": len(effective_test_files),
    }
    return out_tests, total, final_ok, expected_count, generated_count, failures, artifacts
