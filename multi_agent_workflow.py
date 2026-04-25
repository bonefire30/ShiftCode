"""
Multi-file Java->Go project migration: architect -> HITL -> module translate (layered) ->
merge -> test-gen by module -> review -> global_repair / test_gen_repair.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

try:
    from langgraph.types import Command
except Exception:  # noqa: BLE001
    Command = None  # type: ignore[assignment, misc]
try:
    from langgraph.types import interrupt
except Exception:  # noqa: BLE001
    interrupt = None  # type: ignore[assignment, misc]

from codebase_rag import make_rag
from dependency_graph import (
    build_dependency_graph,
    cluster_into_modules,
    module_dependency_layers,
    topological_batches,
)
from java_ast import (
    detect_framework_flags,
    java_info_to_dict,
    parse_java_file,
)
from project_tools import go_build_status, go_test_status, init_go_module, scan_java_project
from symbol_table import SymbolTable
from logging_config import (
    attach_per_run_file_handler,
    detach_per_run_file_handler,
    node_logger,
    reset_workflow_thread_id,
    set_workflow_thread_id,
    setup_logging,
)
from workflow import run_module_agent, run_test_gen_module_agent
from test_quality_guard import (
    evaluate_test_quality,
    extract_prompt_contract_checklist,
)

ROOT = Path(__file__).resolve().parent
setup_logging()
_wf = logging.getLogger("shiftcode.workflow")
INTERRUPT_OK = interrupt is not None
COMMAND_OK = Command is not None


class FileTranslationState(TypedDict, total=False):
    java_path: str
    go_code: str
    status: str
    errors: list[str]
    attempts: int
    last_error_hint: str


class MultiProjectState(TypedDict, total=False):
    project_dir: str
    go_output_dir: str
    go_module: str
    java_files: list[str]
    java_infos: dict[str, Any]
    dependency_graph: dict[str, list[str]]
    symbol_table_data: dict[str, Any]
    type_mappings: dict[str, str]
    translation_batches: list[list[str]]
    modules: list[list[str]]
    current_batch_idx: int
    file_states: dict[str, FileTranslationState]
    test_gen_states: dict[str, str]
    module_translate_artifacts: dict[str, dict[str, Any]]
    module_test_gen_artifacts: dict[str, dict[str, Any]]
    framework_flags: list[str]
    hitl_decisions: dict[str, str]
    last_build_ok: bool
    last_test_ok: bool
    last_build_log: str
    repair_round: int
    max_repair_rounds: int
    total_tokens: int
    migration_done: bool
    fatal: str
    test_gen_failures: list[str]
    test_gen_expected_count: int
    test_gen_generated_count: int
    test_gen_ok: bool
    test_gen_warnings: list[str]
    test_quality_ok: bool


def _java_to_go_relpath(java_rel: str) -> str:
    p = java_rel.replace("\\", "/")
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


def _go_package_name(java_rel: str) -> str:
    parts = java_rel.replace("\\", "/").split("/")
    if len(parts) >= 2:
        d = parts[-2]
        valid = re.sub(r"[^a-zA-Z0-9_]", "_", d).lower() or "pkg"
        if valid and valid[0].isdigit():
            return "p" + valid
        return valid
    return "main"


def _extract_package_from_prompt(prompt: str) -> str | None:
    """
    Best-effort parse of `package foo` or package `foo` from migration_prompt.txt.
    """
    if not (prompt or "").strip():
        return None
    m = re.search(r"package\s+`(\w+)`", prompt)
    if m:
        return m.group(1)
    m2 = re.search(
        r"(?im)^\s*Output\s+exactly\s+one\s+file:\s*package\s+`(\w+)`",
        prompt,
    )
    if m2:
        return m2.group(1)
    m3 = re.search(
        r"(?im)package\s+`?(\w+)`?\s+with",
        prompt,
    )
    if m3:
        return m3.group(1)
    return None


def architect_node(state: MultiProjectState) -> dict[str, Any]:
    log = node_logger("architect")
    raw0 = (state.get("project_dir") or "").strip().replace("\\", "/")
    log.info("进入节点 project_dir=%s", raw0)
    t0 = time.perf_counter()
    raw = raw0
    if not raw:
        log.error("fatal: missing project_dir")
        return {"fatal": "missing project_dir", "migration_done": True}
    pr = (ROOT / raw).resolve()
    rres = ROOT.resolve()
    if not str(pr).startswith(str(rres)) or not pr.is_dir():
        log.error("fatal: invalid project_dir=%r", raw)
        return {"fatal": f"invalid project_dir: {raw!r}", "migration_done": True}
    jfiles = scan_java_project(pr)
    if not jfiles:
        log.error("fatal: no .java under project")
        return {"fatal": "no .java files under project", "migration_done": True}
    infos: list[Any] = []
    info_map: dict[str, Any] = {}
    for j in jfiles:
        fi = parse_java_file(pr, pr / j.replace("/", os.sep))
        infos.append(fi)
        info_map[j] = java_info_to_dict(fi)
    g = build_dependency_graph(infos)
    batches = topological_batches(g, jfiles)
    modules = cluster_into_modules(infos, g)
    if not modules and jfiles:
        modules = [[j] for j in jfiles]
    st = SymbolTable()
    for i in infos:
        st.register(i)
    out_dir = ROOT / "project_migrations" / f"out_{uuid.uuid4().hex[:12]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    mod = state.get("go_module") or f"m.shiftcode.migrated/{out_dir.name}"
    init_msg = init_go_module(out_dir, mod)
    fstates: dict[str, FileTranslationState] = {
        p: {
            "java_path": p,
            "status": "pending",
            "go_code": "",
            "errors": [],
            "attempts": 0,
        }
        for p in jfiles
    }
    ff = detect_framework_flags(infos)
    log.info(
        "退出节点 耗时=%.3fs java_files=%d batches=%d modules=%d go_output_dir=%s framework_flags=%s",
        time.perf_counter() - t0,
        len(jfiles),
        len(batches),
        len(modules),
        str(out_dir),
        ff,
    )
    return {
        "java_files": jfiles,
        "java_infos": info_map,
        "dependency_graph": g,
        "translation_batches": batches,
        "modules": modules,
        "current_batch_idx": 0,
        "symbol_table_data": st.to_dict(),
        "type_mappings": dict(SymbolTable.java_to_go_types()),
        "file_states": fstates,
        "test_gen_states": {},
        "module_translate_artifacts": {},
        "module_test_gen_artifacts": {},
        "go_output_dir": str(out_dir),
        "go_module": mod,
        "framework_flags": ff,
        "last_build_log": init_msg,
        "repair_round": 0,
        "max_repair_rounds": int(state.get("max_repair_rounds") or 3),
        "test_gen_failures": [],
        "test_gen_expected_count": 0,
        "test_gen_generated_count": 0,
        "test_gen_ok": False,
        "test_gen_warnings": [],
        "test_quality_ok": False,
    }


def hitl_gateway_node(state: MultiProjectState) -> dict[str, Any]:
    log = node_logger("hitl_gateway")
    flags = state.get("framework_flags") or []
    decs: dict[str, str] = dict(state.get("hitl_decisions") or {})
    log.info("进入节点 framework_flags=%s hitl_decisions_keys=%s", flags, list(decs))
    if not flags:
        log.info("无框架标记，跳过人机确认")
        return {"hitl_decisions": decs}
    if not INTERRUPT_OK:
        for f in flags:
            decs.setdefault(f"fw_{f}", "accept_defaults")
        log.warning("interrupt 不可用，自动使用 accept_defaults flags=%s", flags)
        return {"hitl_decisions": decs}
    for f in flags:
        k = f"fw_{f}"
        if k in decs:
            continue
        q = f"Framework '{f}' detected. Use conservative idiomatic-Go strategy?"
        log.info("HITL interrupt: key=%s framework=%s", k, f)
        d = cast(Any, interrupt)(
            {"key": k, "question": q, "framework": f, "type": "hitl"},
        )
        log.info("HITL 收到决策 key=%s", k)
        return {"hitl_decisions": {**decs, k: d}}
    log.info("退出节点，所有框架决策已就绪")
    return {"hitl_decisions": decs}


def _build_go_package_map(
    project_migration_prompt: str, module_files: list[str]
) -> dict[str, str]:
    ovr = _extract_package_from_prompt(project_migration_prompt)
    return {
        jr: (ovr or _go_package_name(jr)) for jr in module_files
    }


def _translate_one_module(
    *,
    mod_idx: int,
    mod_files: list[str],
    pr: Path,
    go_out: Path,
    st: SymbolTable,
    tmaps: dict[str, str],
    project_migration_prompt: str,
    ragger: Any,
    err_hints: dict[str, str],
    prev_states: dict[str, FileTranslationState],
    rag_lock: threading.Lock,
) -> tuple[dict[str, FileTranslationState], int, dict[str, Any]]:
    log = node_logger("translate_modules")
    label = f"mod{mod_idx}"
    java_sources: dict[str, str] = {}
    for jr in mod_files:
        jpath = pr / jr.replace("/", os.sep)
        if not jpath.is_file():
            java_sources[jr] = ""
            continue
        info = parse_java_file(pr, jpath)
        java_sources[jr] = info.source_text
    go_pkg_map = _build_go_package_map(project_migration_prompt, mod_files)
    ctx_parts: list[str] = []
    first_q: str = ""
    for jr in mod_files:
        jpath = pr / jr.replace("/", os.sep)
        if not jpath.is_file():
            continue
        info = parse_java_file(pr, jpath)
        ctx_parts.append(
            f"#### {jr}\n{st.context_for(info)}"
        )
        if not first_q and (info.classes or [jr]):
            first_q = str(info.classes[0] if info.classes else jr)
    rag_block = ""
    if ragger and first_q:
        with rag_lock:
            examples2 = ragger.query(f"Context for {first_q}", k=2)
        if examples2:
            rag_block = "\n#### RAG\n" + "\n---\n".join(examples2)
    base_maps = {**SymbolTable.java_to_go_types(), **(tmaps or {})}
    type_block = "\n".join(f"- {a} => {b}" for a, b in list(base_maps.items())[:20])
    err0 = (err_hints.get(mod_files[0]) or "").strip() if mod_files else ""
    context_hint = (
        f"### SymbolTable / per-file context\n" + "\n".join(ctx_parts) + "\n"
        f"### TypeMappings (sample)\n{type_block}\n"
        f"{rag_block}"
    )
    fstates: dict[str, FileTranslationState] = {}
    used_tok = 0
    try:
        out_map, used_tok, success, artifacts = run_module_agent(
            module_dep_order=mod_files,
            java_sources=java_sources,
            go_output_dir=go_out,
            go_package_map=go_pkg_map,
            module_name=label,
            context_hint=context_hint,
            err_hint=err0,
            system_prompt_override=project_migration_prompt,
        )
    except Exception as e:  # noqa: BLE001
        log.error("run_module_agent 失败 mod=%s", label, exc_info=True)
        for jr in mod_files:
            prev = dict(prev_states.get(jr) or {})
            fstates[jr] = {
                "java_path": jr,
                "go_code": "",
                "status": "failed",
                "errors": [str(e)],
                "attempts": int(prev.get("attempts") or 0) + 1,
            }
        return fstates, 0, {
            "written_files": [],
            "detected_new_or_changed_files": [],
            "effective_output_files": [],
            "declared_count": 0,
            "diff_count": 0,
            "effective_count": 0,
        }
    for jr in mod_files:
        prev = dict(prev_states.get(jr) or {})
        fs0: FileTranslationState = {
            "java_path": jr,
            "go_code": (out_map.get(jr) or "").strip(),
            "status": "done" if success else "partial",
            "errors": [],
            "attempts": int(prev.get("attempts") or 0) + 1,
        }
        fstates[jr] = fs0
    if success and out_map:
        with rag_lock:
            for jr, go in out_map.items():
                if (go or "").strip():
                    ragger.add_file(jr, go)
    log.info(
        "run_module_agent 完成 mod=%s success=%s declared_count=%d diff_count=%d effective_count=%d",
        label,
        success,
        int(artifacts.get("declared_count") or 0),
        int(artifacts.get("diff_count") or 0),
        int(artifacts.get("effective_count") or 0),
    )
    return fstates, used_tok, artifacts


def translate_modules_node(state: MultiProjectState) -> dict[str, Any]:
    log = node_logger("translate_modules")
    if state.get("fatal"):
        log.warning("跳过：存在 fatal，直接返回空更新")
        return {}
    pr = (ROOT / (state.get("project_dir") or "")).resolve()
    go_out = Path(state.get("go_output_dir") or "")
    if not go_out.is_dir():
        log.error("fatal: missing go_output_dir")
        return {"fatal": "missing go_output_dir", "migration_done": True}
    st = SymbolTable.from_dict(state.get("symbol_table_data") or {})
    tmaps: dict[str, str] = dict(
        (state.get("type_mappings") or SymbolTable.java_to_go_types()) or {}
    )
    _prompt_file = pr / "migration_prompt.txt"
    project_migration_prompt = (
        _prompt_file.read_text(encoding="utf-8").strip()
        if _prompt_file.is_file()
        else ""
    )
    ragger = make_rag()
    fstates0: dict[str, FileTranslationState] = dict(state.get("file_states") or {})
    fstates: dict[str, FileTranslationState] = dict(fstates0)
    module_translate_artifacts: dict[str, dict[str, Any]] = dict(
        state.get("module_translate_artifacts") or {}
    )
    err_hints = {p: (fs.get("last_error_hint") or "") for p, fs in fstates0.items()}

    modules = state.get("modules") or []
    g = state.get("dependency_graph") or {}
    layers = module_dependency_layers(modules, g) if modules else []
    log.info("进入节点 modules=%d 层数=%d", len(modules), len(layers))
    tok = int(state.get("total_tokens") or 0)
    workers = int(os.environ.get("TRANSLATE_WORKERS", "4"))
    rag_lock = threading.Lock()
    for layer in layers:
        if not layer:
            continue
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {
                ex.submit(
                    _translate_one_module,
                    mod_idx=midx,
                    mod_files=modules[midx],
                    pr=pr,
                    go_out=go_out,
                    st=st,
                    tmaps=tmaps,
                    project_migration_prompt=project_migration_prompt,
                    ragger=ragger,
                    err_hints=err_hints,
                    prev_states=fstates0,
                    rag_lock=rag_lock,
                ): midx
                for midx in layer
            }
            for fut in as_completed(futs):
                midx = futs[fut]
                mpart, tadd, marts = fut.result()
                tok += tadd
                fstates.update(mpart)
                module_translate_artifacts[f"mod{midx}"] = marts
    log.info("退出节点 total_tokens=%d", tok)
    return {
        "file_states": fstates,
        "total_tokens": tok,
        "module_translate_artifacts": module_translate_artifacts,
    }


def merge_all_node(state: MultiProjectState) -> dict[str, Any]:
    log = node_logger("merge_all")
    st = SymbolTable.from_dict(state.get("symbol_table_data") or {})
    jmap = state.get("java_infos") or {}
    n_registered = 0
    for p, f in (state.get("file_states") or {}).items():
        g = f.get("go_code") or ""
        jd: Any = jmap.get(p) or {}
        if isinstance(jd, dict):
            for c in jd.get("classes") or []:
                st.register_go(c, g)
                n_registered += 1
    log.info("合并符号表 register_go 调用次数=%d", n_registered)
    return {"symbol_table_data": st.to_dict()}


def _test_gen_one_module(
    midx: int,
    mod_files: list[str],
    pr: Path,
    go_out: Path,
    project_migration_prompt: str,
    prompt_contract_checklist: list[str],
    err_hint: str,
    translate_artifacts: dict[str, Any],
) -> tuple[dict[str, str], int, bool, int, int, list[str], list[str], dict[str, Any]]:
    log = node_logger("test_gen_modules")
    java_sources: dict[str, str] = {}
    for jr in mod_files:
        jpath = pr / jr.replace("/", os.sep)
        if not jpath.is_file():
            java_sources[jr] = ""
            continue
        info = parse_java_file(pr, jpath)
        java_sources[jr] = info.source_text
    module_java_lc = "\n".join(java_sources.values()).lower()

    def _module_checklist_items(all_items: list[str]) -> list[str]:
        if not all_items:
            return []
        keep: list[str] = []
        for item in all_items:
            low = item.lower()
            if "runpayment" in low and "runpayment" not in module_java_lc:
                continue
            if "logtransaction" in low and "logtransaction" not in module_java_lc:
                continue
            if "field id" in low and " id" not in module_java_lc and "id " not in module_java_lc:
                continue
            keep.append(item)
        return keep

    module_checklist = _module_checklist_items(prompt_contract_checklist)
    go_map = _build_go_package_map(project_migration_prompt, mod_files)
    label = f"mod{midx}"
    try:
        expected_go_files = list(translate_artifacts.get("effective_output_files") or [])
        out, used, ok, expected_count, generated_count, failures, test_artifacts = run_test_gen_module_agent(
            module_dep_order=mod_files,
            java_sources=java_sources,
            go_output_dir=go_out,
            go_package_map=go_map,
            migration_prompt_text=project_migration_prompt,
            prompt_contract_checklist=module_checklist,
            expected_go_files=expected_go_files,
            module_name=label,
            err_hint=err_hint,
        )
    except Exception as e:  # noqa: BLE001
        log.error("run_test_gen_module_agent 失败 %s", label, exc_info=True)
        return (
            {},
            0,
            False,
            len(mod_files),
            0,
            [f"module {label}: {e}"],
            [],
            {
                "written_files": [],
                "detected_new_or_changed_files": [],
                "effective_output_files": [],
                "expected_output_files": [],
                "declared_count": 0,
                "diff_count": 0,
                "effective_count": 0,
            },
        )

    go_sources: dict[str, str] = {}
    effective_go_files = list(translate_artifacts.get("effective_output_files") or [])
    if not effective_go_files:
        effective_go_files = [_java_to_go_relpath(jr) for jr in mod_files]
    for gr in effective_go_files:
        gp = go_out / gr
        go_sources[gr] = gp.read_text(encoding="utf-8", errors="replace") if gp.is_file() else ""

    quality_failures, quality_warnings, quality_ok = evaluate_test_quality(
        module_name=label,
        prompt_text=project_migration_prompt,
        prompt_contract_checklist=module_checklist,
        java_sources=java_sources,
        go_sources=go_sources,
        generated_tests=out,
    )
    merged_failures = [*failures, *quality_failures]
    return (
        out,
        used,
        ok and quality_ok and not merged_failures,
        expected_count,
        generated_count,
        merged_failures,
        quality_warnings,
        test_artifacts,
    )


def _summarize_test_gen_state(
    *,
    tok: int,
    tgen: dict[str, str],
    expected_count: int,
    generated_count: int,
    failures: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    quality_failures = [
        f
        for f in failures
        if f.startswith("over_specified_tests:") or f.startswith("missing_required_assertions:")
    ]
    return {
        "test_gen_states": tgen,
        "total_tokens": tok,
        "test_gen_expected_count": expected_count,
        "test_gen_generated_count": generated_count,
        "test_gen_failures": failures,
        "test_gen_warnings": warnings,
        "test_quality_ok": not quality_failures,
        "test_gen_ok": expected_count > 0 and generated_count == expected_count and not failures,
    }


def _global_repair_one_module(
    mod_idx: int,
    mod_files: list[str],
    pr: Path,
    go_out: Path,
    st: SymbolTable,
    tmaps: dict[str, str],
    project_migration_prompt: str,
    err_hint: str,
    ragger: Any,
    prev_states: dict[str, FileTranslationState],
    rag_lock: threading.Lock,
) -> tuple[dict[str, FileTranslationState], int, dict[str, Any]]:
    if not mod_files:
        return {}, 0, {
            "written_files": [],
            "detected_new_or_changed_files": [],
            "effective_output_files": [],
            "declared_count": 0,
            "diff_count": 0,
            "effective_count": 0,
        }
    java_sources: dict[str, str] = {}
    for jr in mod_files:
        jpath = pr / jr.replace("/", os.sep)
        if not jpath.is_file():
            java_sources[jr] = ""
            continue
        info = parse_java_file(pr, jpath)
        java_sources[jr] = info.source_text
    go_pkg_map = _build_go_package_map(project_migration_prompt, mod_files)
    label = f"mod{mod_idx}"
    ctx_parts: list[str] = []
    first_q: str = ""
    for jr in mod_files:
        jpath = pr / jr.replace("/", os.sep)
        if not jpath.is_file():
            continue
        info = parse_java_file(pr, jpath)
        ctx_parts.append(f"#### {jr}\n{st.context_for(info)}")
        if not first_q and (info.classes or [jr]):
            first_q = str(info.classes[0] if info.classes else jr)
    rag_block = ""
    if ragger and first_q:
        with rag_lock:
            examples = ragger.query(f"Context for {first_q}", k=2)
        if examples:
            rag_block = "\n#### RAG\n" + "\n---\n".join(examples)
    base_maps = {**SymbolTable.java_to_go_types(), **(tmaps or {})}
    type_block = "\n".join(f"- {a} => {b}" for a, b in list(base_maps.items())[:20])
    context_hint = (
        f"### SymbolTable (repair)\n" + "\n".join(ctx_parts) + "\n"
        f"### TypeMappings (sample)\n{type_block}\n"
        f"{rag_block}\n"
        "### REPAIR: fix so `go build ./...` and tests can succeed. Prefer minimal edits."
    )
    fstates: dict[str, FileTranslationState] = {}
    try:
        out_map, used_tok, success, artifacts = run_module_agent(
            module_dep_order=mod_files,
            java_sources=java_sources,
            go_output_dir=go_out,
            go_package_map=go_pkg_map,
            module_name=label,
            context_hint=context_hint,
            err_hint=err_hint,
            system_prompt_override=project_migration_prompt,
        )
    except Exception as e:  # noqa: BLE001
        for jr in mod_files:
            prev = dict(prev_states.get(jr) or {})
            fstates[jr] = {
                "java_path": jr,
                "go_code": "",
                "status": "failed",
                "errors": [str(e)],
                "attempts": int(prev.get("attempts") or 0) + 1,
            }
        return fstates, 0, {
            "written_files": [],
            "detected_new_or_changed_files": [],
            "effective_output_files": [],
            "declared_count": 0,
            "diff_count": 0,
            "effective_count": 0,
        }
    for jr in mod_files:
        prev2 = dict(prev_states.get(jr) or {})
        fstates[jr] = {
            "java_path": jr,
            "go_code": (out_map.get(jr) or "").strip(),
            "status": "done" if success else "partial",
            "errors": [],
            "attempts": int(prev2.get("attempts") or 0) + 1,
        }
    if success and out_map:
        with rag_lock:
            for jr, g in out_map.items():
                if (g or "").strip():
                    ragger.add_file(jr, g)
    return fstates, used_tok, artifacts


def global_repair_node(state: MultiProjectState) -> dict[str, Any]:
    """Re-run `run_module_agent` for each module with last build log as err_hint."""
    log = node_logger("global_repair")
    pr = (ROOT / (state.get("project_dir") or "")).resolve()
    go_out = Path(state.get("go_output_dir") or "")
    blog = (state.get("last_build_log") or "")[:8000]
    log.info(
        "global_repair 开始 摘要(500): %s", (blog or "")[:500].replace("\n", "\\n")
    )
    if not go_out.is_dir():
        return {"last_build_log": (state.get("last_build_log") or "") + "\n[global_repair: no go_output_dir]"}
    _prompt_file = pr / "migration_prompt.txt"
    project_migration_prompt = (
        _prompt_file.read_text(encoding="utf-8").strip()
        if _prompt_file.is_file()
        else ""
    )
    st = SymbolTable.from_dict(state.get("symbol_table_data") or {})
    tmaps: dict[str, str] = dict(
        (state.get("type_mappings") or SymbolTable.java_to_go_types()) or {}
    )
    fstates0: dict[str, FileTranslationState] = dict(state.get("file_states") or {})
    fstates: dict[str, FileTranslationState] = dict(fstates0)
    module_translate_artifacts: dict[str, dict[str, Any]] = dict(
        state.get("module_translate_artifacts") or {}
    )
    tok = int(state.get("total_tokens") or 0)
    modules = state.get("modules") or []
    ragger = make_rag()
    for _p, fs0 in fstates0.items():
        g0 = (fs0.get("go_code") or "").strip()
        if g0:
            ragger.add_file(_p, g0)
    workers = int(os.environ.get("TRANSLATE_WORKERS", "4"))
    rag_lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(
                _global_repair_one_module,
                midx,
                mod,
                pr,
                go_out,
                st,
                tmaps,
                project_migration_prompt,
                blog,
                ragger,
                fstates0,
                rag_lock,
            ): midx
            for midx, mod in enumerate(modules)
        }
        for fut in as_completed(futs):
            midx = futs[fut]
            mpart, tadd, marts = fut.result()
            tok += tadd
            fstates.update(mpart)
            module_translate_artifacts[f"mod{midx}"] = marts
    prev = state.get("last_build_log") or ""
    return {
        "file_states": fstates,
        "total_tokens": tok,
        "module_translate_artifacts": module_translate_artifacts,
        "last_build_log": prev + "\n[global_repair: module agent 重试一轮]",
    }


def _run_test_gen_stage(
    state: MultiProjectState,
    *,
    err_hint: str,
    node_name: str,
    repair_only_failed: bool = False,
) -> dict[str, Any]:
    log = node_logger(node_name)
    if state.get("fatal"):
        return {}
    pr = (ROOT / (state.get("project_dir") or "")).resolve()
    go_out = Path(state.get("go_output_dir") or "")
    if not go_out.is_dir():
        return {"fatal": "missing go_output_dir", "migration_done": True}
    _prompt_file = pr / "migration_prompt.txt"
    project_migration_prompt = (
        _prompt_file.read_text(encoding="utf-8").strip()
        if _prompt_file.is_file()
        else ""
    )
    prompt_contract_checklist = extract_prompt_contract_checklist(project_migration_prompt)
    modules = state.get("modules") or []
    tok = int(state.get("total_tokens") or 0)
    tgen: dict[str, str] = dict(state.get("test_gen_states") or {})
    module_translate_artifacts: dict[str, dict[str, Any]] = dict(
        state.get("module_translate_artifacts") or {}
    )
    module_test_gen_artifacts: dict[str, dict[str, Any]] = dict(
        state.get("module_test_gen_artifacts") or {}
    )
    previous_tgen: dict[str, str] = dict(state.get("test_gen_states") or {})
    previous_failures = list(state.get("test_gen_failures") or [])
    modules_to_run: list[tuple[int, list[str]]] = list(enumerate(modules))
    if repair_only_failed and previous_failures:
        failed_module_ids: set[int] = set()
        for failure in previous_failures:
            for match in re.finditer(r"\bmod(\d+)\b", str(failure)):
                failed_module_ids.add(int(match.group(1)))
        if failed_module_ids:
            modules_to_run = [
                (midx, mod)
                for midx, mod in enumerate(modules)
                if midx in failed_module_ids
            ]
    expected_count = 0
    generated_count = 0
    failures: list[str] = []
    warnings: list[str] = []
    declared_count = 0
    diff_count = 0
    effective_count = 0
    workers = int(os.environ.get("TEST_GEN_WORKERS", "8"))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(
                _test_gen_one_module,
                midx,
                mod,
                pr,
                go_out,
                project_migration_prompt,
                prompt_contract_checklist,
                err_hint,
                module_translate_artifacts.get(f"mod{midx}") or {},
            ): midx
            for midx, mod in modules_to_run
        }
        for fut in as_completed(futs):
            midx = futs[fut]
            (
                out,
                tadd,
                ok,
                expected_add,
                generated_add,
                module_failures,
                module_warnings,
                module_artifacts,
            ) = fut.result()
            tok += tadd
            tgen.update(out)
            expected_count += expected_add
            generated_count += generated_add
            declared_count += int(module_artifacts.get("declared_count") or 0)
            diff_count += int(module_artifacts.get("diff_count") or 0)
            effective_count += int(module_artifacts.get("effective_count") or 0)
            module_test_gen_artifacts[f"mod{midx}"] = module_artifacts
            if not ok:
                failures.extend(module_failures)
            warnings.extend(module_warnings)
    if repair_only_failed:
        ran_module_labels = {f"mod{midx}" for midx, _mod in modules_to_run}
        for midx, _mod in enumerate(modules):
            label = f"mod{midx}"
            if label in ran_module_labels:
                continue
            prev_artifacts = module_test_gen_artifacts.get(label) or {}
            prev_effective = [
                str(p)
                for p in (prev_artifacts.get("effective_output_files") or [])
                if str(p).endswith("_test.go")
            ]
            prev_expected = [
                str(p)
                for p in (prev_artifacts.get("expected_output_files") or [])
                if str(p).endswith("_test.go")
            ]
            if not prev_expected:
                prev_expected = prev_effective
            expected_count += len(prev_expected)
            generated_count += len(prev_effective)
            effective_count += len(prev_effective)
            for test_path in prev_effective:
                if test_path in previous_tgen:
                    tgen[test_path] = previous_tgen[test_path]
    log.info(
        "%s completed total_tokens~=%d expected_tests=%d generated_tests=%d declared_count=%d diff_count=%d effective_count=%d failed_modules=%d",
        node_name,
        tok,
        expected_count,
        generated_count,
        declared_count,
        diff_count,
        effective_count,
        len(failures),
    )
    out = _summarize_test_gen_state(
        tok=tok,
        tgen=tgen,
        expected_count=expected_count,
        generated_count=generated_count,
        failures=failures,
        warnings=warnings,
    )
    out["module_test_gen_artifacts"] = module_test_gen_artifacts
    return out


def test_gen_modules_node(state: MultiProjectState) -> dict[str, Any]:
    return _run_test_gen_stage(state, err_hint="", node_name="test_gen_modules")


def test_gen_repair_node(state: MultiProjectState) -> dict[str, Any]:
    go_out = Path(state.get("go_output_dir") or "")
    if not go_out.is_dir():
        return {}
    blog = (state.get("last_build_log") or "")[:8000]
    failures = "\n".join(str(f) for f in (state.get("test_gen_failures") or []))
    err_hint = (
        "The Go implementation compiles. Fix only tests and test assumptions (imports, package, "
        "API names, contract assertions). Do not modify Go source files. Preserve existing passing "
        "tests; only create missing test files or edit files directly implicated by the failures.\n"
        "Current test generation failures:\n"
        + (failures or "(none)")
        + "\nFull log below.\n"
        + blog
    )
    return _run_test_gen_stage(
        state,
        err_hint=err_hint,
        node_name="test_gen_repair",
        repair_only_failed=True,
    )


def reviewer_node(state: MultiProjectState) -> dict[str, Any]:
    log = node_logger("reviewer")
    go_out = Path(state.get("go_output_dir") or "")
    test_state = {
        "test_gen_ok": bool(state.get("test_gen_ok", False)),
        "test_gen_failures": list(state.get("test_gen_failures") or []),
        "test_gen_warnings": list(state.get("test_gen_warnings") or []),
        "test_quality_ok": bool(state.get("test_quality_ok", False)),
        "test_gen_expected_count": int(state.get("test_gen_expected_count") or 0),
        "test_gen_generated_count": int(state.get("test_gen_generated_count") or 0),
    }
    if not go_out.is_dir():
        log.error("reviewer missing go_output_dir")
        return {
            "last_build_ok": False,
            "last_test_ok": False,
            "last_build_log": "no output dir",
            "migration_done": True,
            **test_state,
        }
    ok, blog = go_build_status(go_out)
    rep = int(state.get("repair_round") or 0)
    fstates: dict[str, FileTranslationState] = dict(state.get("file_states") or {})
    all_paths = list(fstates.keys())
    if not ok:
        hint = (blog or "")[:8000]
        log.warning("go build failed repair_round=%d->%d", rep, rep + 1)
        for p in all_paths:
            fs = dict(fstates.get(p) or {"java_path": p})
            fs["last_error_hint"] = hint
            fstates[p] = fs
        return {
            "last_build_ok": False,
            "last_test_ok": False,
            "last_build_log": blog,
            "file_states": fstates,
            "repair_round": rep + 1,
            **test_state,
        }

    test_gen_ok = bool(test_state["test_gen_ok"])
    test_quality_ok = bool(test_state["test_quality_ok"])
    test_failures = list(test_state["test_gen_failures"])
    expected_count = int(test_state["test_gen_expected_count"])
    generated_count = int(test_state["test_gen_generated_count"])
    missing_source_files: list[str] = []
    if test_failures:
        for failure in test_failures:
            for test_path in re.findall(r"[\w./-]+_test\.go", str(failure)):
                source_path = test_path[: -len("_test.go")] + ".go"
                if not (go_out / source_path).is_file():
                    missing_source_files.append(source_path)
    if not test_gen_ok or not test_quality_ok:
        over_specs = [
            f for f in test_failures if f.startswith("over_specified_tests:")
        ]
        missing_required = [
            f for f in test_failures if f.startswith("missing_required_assertions:")
        ]
        summary = (
            f"Generated tests incomplete: expected={expected_count}, generated={generated_count}."
        )
        details = "\n".join(test_failures) if test_failures else "No detailed test generation failures recorded."
        combined = (
            "--- go build OK ---\n"
            + (blog or "")
            + "\n--- test generation incomplete ---\n"
            + summary
            + f"\nover_specified_tests={len(over_specs)}"
            + f"\nmissing_required_assertions={len(missing_required)}"
            + (
                "\nmissing_go_sources_for_tests=" + ", ".join(sorted(set(missing_source_files)))
                if missing_source_files
                else ""
            )
            + "\n"
            + details
        )
        hint = combined[:8000]
        log.warning(
            "test generation incomplete repair_round=%d->%d expected=%d generated=%d failures=%d",
            rep,
            rep + 1,
            expected_count,
            generated_count,
            len(test_failures),
        )
        for p in all_paths:
            fs = dict(fstates.get(p) or {"java_path": p})
            fs["last_error_hint"] = hint
            fstates[p] = fs
        return {
            "last_build_ok": True,
            "last_test_ok": False,
            "last_build_log": combined,
            "file_states": fstates,
            "missing_source_files_for_tests": sorted(set(missing_source_files)),
            "repair_round": rep + 1,
            **test_state,
        }

    test_ok, test_log = go_test_status(go_out)
    if not test_ok:
        hint = (test_log or "")[:8000]
        combined = (
            "--- go build OK ---\n"
            + (blog or "")
            + "\n--- go test FAILED ---\n"
            + (test_log or "")
        )
        log.warning("go test failed repair_round=%d->%d", rep, rep + 1)
        for p in all_paths:
            fs = dict(fstates.get(p) or {"java_path": p})
            fs["last_error_hint"] = hint
            fstates[p] = fs
        return {
            "last_build_ok": True,
            "last_test_ok": False,
            "last_build_log": combined,
            "file_states": fstates,
            "repair_round": rep + 1,
            **test_state,
        }

    log.info(
        "go build + go test succeeded repair_round reset expected_tests=%d generated_tests=%d failures=%d",
        expected_count,
        generated_count,
        len(test_failures),
    )
    return {
        "last_build_ok": True,
        "last_test_ok": True,
        "last_build_log": (blog or "OK") + "\n--- go test ---\n" + (test_log or ""),
        "repair_round": 0,
        **test_state,
    }


def route_after_reviewer(
    state: MultiProjectState,
) -> Literal["end", "global_repair", "test_gen_repair"]:
    if state.get("fatal") or state.get("migration_done"):
        _wf.info(
            "route_after_reviewer -> end (fatal=%s migration_done=%s)",
            state.get("fatal"),
            state.get("migration_done"),
        )
        return "end"
    build_ok = bool(state.get("last_build_ok", False))
    test_ok = bool(state.get("last_test_ok", True))
    test_gen_ok = bool(state.get("test_gen_ok", False))
    test_quality_ok = bool(state.get("test_quality_ok", False))
    missing_source_files = list(state.get("missing_source_files_for_tests") or [])
    max_r = int(state.get("max_repair_rounds") or 3)
    rr = int(state.get("repair_round") or 0)
    if not build_ok:
        if rr < max_r:
            _wf.info("route_after_reviewer -> global_repair (build failed rr=%d max=%d)", rr, max_r)
            return "global_repair"
        _wf.info("route_after_reviewer -> end (build failed rr=%d max=%d)", rr, max_r)
        return "end"
    if not test_gen_ok or not test_quality_ok:
        if missing_source_files and rr < max_r:
            _wf.info(
                "route_after_reviewer -> global_repair (missing sources for tests rr=%d max=%d)",
                rr,
                max_r,
            )
            return "global_repair"
        if rr < max_r:
            _wf.info(
                "route_after_reviewer -> test_gen_repair (tests quality/boundary issue rr=%d max=%d)",
                rr,
                max_r,
            )
            return "test_gen_repair"
        _wf.info("route_after_reviewer -> end (tests quality/boundary issue rr=%d max=%d)", rr, max_r)
        return "end"
    if not test_ok:
        if rr < max_r and rr <= (max_r // 2):
            _wf.info(
                "route_after_reviewer -> global_repair (test failure early rr=%d max=%d half=%d)",
                rr,
                max_r,
                max_r // 2,
            )
            return "global_repair"
        if rr < max_r:
            _wf.info("route_after_reviewer -> test_gen_repair (test failure rr=%d max=%d)", rr, max_r)
            return "test_gen_repair"
        _wf.info("route_after_reviewer -> end (test failure rr=%d max=%d)", rr, max_r)
        return "end"
    _wf.info("route_after_reviewer -> end (success)")
    return "end"


def build_project_graph() -> Any:
    g = StateGraph(MultiProjectState)
    g.add_node("architect", architect_node)
    g.add_node("hitl_gateway", hitl_gateway_node)
    g.add_node("translate_modules", translate_modules_node)
    g.add_node("merge_all", merge_all_node)
    g.add_node("test_gen_modules", test_gen_modules_node)
    g.add_node("reviewer", reviewer_node)
    g.add_node("global_repair", global_repair_node)
    g.add_node("test_gen_repair", test_gen_repair_node)
    g.add_edge(START, "architect")
    g.add_edge("architect", "hitl_gateway")
    g.add_edge("hitl_gateway", "translate_modules")
    g.add_edge("translate_modules", "merge_all")
    g.add_edge("merge_all", "test_gen_modules")
    g.add_edge("test_gen_modules", "reviewer")
    g.add_conditional_edges(
        "reviewer",
        route_after_reviewer,
        {
            "global_repair": "global_repair",
            "test_gen_repair": "test_gen_repair",
            "end": END,
        },
    )
    g.add_edge("global_repair", "reviewer")
    g.add_edge("test_gen_repair", "reviewer")
    return g.compile(checkpointer=MemorySaver())


def run_project_migrate(
    project_dir: Path,
    thread_id: str,
    config: dict[str, Any] | None = None,
    *,
    max_repair_rounds: int = 3,
    go_module: str | None = None,
) -> Any:
    """Run graph; same thread_id for MemorySaver; resume with resume_project_migrate()."""
    token = set_workflow_thread_id(thread_id)
    try:
        g = build_project_graph()
        cfg: dict[str, Any] = dict(config or {})
        conf = dict(cfg.get("configurable") or {})
        conf.setdefault("thread_id", thread_id)
        cfg["configurable"] = conf
        init: dict[str, Any] = {
            "project_dir": str(project_dir).replace("\\", "/"),
            "max_repair_rounds": max_repair_rounds,
        }
        if go_module:
            init["go_module"] = go_module
        _wf.info(
            "工作流启动 thread_id=%s project=%s max_repair=%s go_module=%s",
            thread_id,
            project_dir,
            max_repair_rounds,
            go_module,
        )
        for step in g.stream(init, cfg):
            if not step:
                continue
            for node_id, out in step.items():
                _wf.debug("节点完成 node=%s", node_id)
                yield str(node_id), {**out, "thread_id": thread_id}
    finally:
        reset_workflow_thread_id(token)


def stream_project_workflow(
    project_dir: Path,
    *,
    max_repair_rounds: int = 3,
    go_module: str | None = None,
) -> Any:
    tid = f"pm-{uuid.uuid4().hex}"
    cfg: dict[str, Any] = {"configurable": {"thread_id": tid}}
    run_log = attach_per_run_file_handler(thread_id=tid, prefix="migration")
    try:
        for node_id, out in run_project_migrate(
            project_dir,
            tid,
            cfg,
            max_repair_rounds=max_repair_rounds,
            go_module=go_module,
        ):
            yield node_id, out
    finally:
        detach_per_run_file_handler(run_log)


def resume_project_migrate(
    command_value: str | dict[str, Any],
    thread_id: str,
) -> Any:
    """After interrupt(), resume the same graph (same thread, MemorySaver)."""
    if not COMMAND_OK or Command is None:
        raise RuntimeError("langgraph Command not available")
    token = set_workflow_thread_id(thread_id)
    run_log = attach_per_run_file_handler(thread_id=thread_id, prefix="resume")
    try:
        g = build_project_graph()
        cfg: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        cmd = Command(resume=command_value)  # type: ignore[call-arg]
        _wf.info("HITL 恢复工作流 thread_id=%s", thread_id)
        for step in g.stream(cmd, cfg):
            if not step:
                continue
            for node_id, out in step.items():
                _wf.debug("恢复步骤 node=%s", node_id)
                yield str(node_id), {**out, "thread_id": thread_id}
    finally:
        detach_per_run_file_handler(run_log)
        reset_workflow_thread_id(token)


def analyze_project(project_dir: Path) -> dict[str, Any]:
    pr = project_dir.resolve()
    r = ROOT.resolve()
    if not str(pr).startswith(str(r)) or not pr.is_dir():
        raise FileNotFoundError("invalid or outside root")
    jfiles = scan_java_project(pr)
    if not jfiles:
        return {"error": "no .java files", "java_files": []}
    infos = [parse_java_file(pr, pr / j.replace("/", os.sep)) for j in jfiles]
    g = build_dependency_graph(infos)
    batches = topological_batches(g, jfiles)
    modules = cluster_into_modules(infos, g)
    if not modules and jfiles:
        modules = [[j] for j in jfiles]
    mod_layers = module_dependency_layers(modules, g) if modules else []
    return {
        "java_files": jfiles,
        "dependency_graph": g,
        "translation_batches": batches,
        "modules": modules,
        "module_layer_count": len(mod_layers),
        "framework_flags": detect_framework_flags(infos),
        "batch_count": len(batches),
    }
