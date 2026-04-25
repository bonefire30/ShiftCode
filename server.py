"""
FastAPI + SSE entrypoint for project-level migration only.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from logging_config import setup_logging
from multi_agent_workflow import (
    COMMAND_OK,
    analyze_project,
    resume_project_migrate,
    stream_project_workflow,
)

setup_logging()
_log = logging.getLogger("shiftcode.server")

ROOT = Path(__file__).resolve().parent

app = FastAPI(title="ShiftCode Migration API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _serialize_project_state(state: dict[str, Any]) -> dict[str, Any]:
    """
    Keep SSE payloads reasonably small.
    """
    out: dict[str, Any] = {}
    for key, value in state.items():
        if key == "java_infos" and isinstance(value, dict):
            infos: dict[str, Any] = {}
            for path, data in value.items():
                if isinstance(data, dict):
                    infos[path] = {**data, "source_text": str(data.get("source_text") or "")[:2000]}
            out[key] = infos
        elif key == "file_states" and isinstance(value, dict):
            file_states: dict[str, Any] = {}
            for path, file_state in value.items():
                if isinstance(file_state, dict):
                    code = str(file_state.get("go_code") or "")
                    file_states[path] = {
                        **file_state,
                        "go_code": code[:2000] + ("..." if len(code) > 2000 else ""),
                    }
                else:
                    file_states[path] = str(file_state)[:200]
            out[key] = file_states
        elif key == "last_build_log" and isinstance(value, str):
            out[key] = value[:8000]
        elif key in {
            "thread_id",
            "fatal",
            "go_module",
            "go_output_dir",
            "project_dir",
            "translation_batches",
            "framework_flags",
            "java_files",
            "dependency_graph",
            "symbol_table_data",
            "current_batch_idx",
            "repair_round",
            "max_repair_rounds",
            "total_tokens",
            "last_build_ok",
            "last_test_ok",
            "hitl_decisions",
            "test_gen_ok",
            "test_gen_expected_count",
            "test_gen_generated_count",
            "test_gen_failures",
            "test_gen_warnings",
            "test_quality_ok",
        }:
            out[key] = value
        elif isinstance(value, (bool, int, float, str)) or value is None:
            out[key] = value
        elif isinstance(value, dict):
            out[key] = value
    return out


def _discover_cases() -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    seen: set[str] = set()
    for prompt_file in sorted(ROOT.glob("benchmark_*/**/migration_prompt.txt")):
        case_dir = prompt_file.parent
        rel = case_dir.relative_to(ROOT)
        path_str = str(rel).replace("\\", "/")
        if path_str in seen:
            continue
        seen.add(path_str)
        cases.append({"id": path_str, "name": case_dir.name, "path": path_str})
    return cases


def _resolve_project_dir(path: str) -> Path:
    root_resolved = ROOT.resolve()
    raw = (ROOT / path).resolve()
    if not str(raw).startswith(str(root_resolved)):
        raise FileNotFoundError("Invalid project path (outside project root)")
    if not raw.is_dir():
        raise FileNotFoundError(f"Not a directory: {path!r}")
    return raw


def _sse_project_migrate(project_rel: str, max_repair: int, go_module: str | None) -> Any:
    project_dir = (ROOT / project_rel).resolve()
    root_dir = ROOT.resolve()
    if not str(project_dir).startswith(str(root_dir)):
        raise FileNotFoundError("Invalid path")
    if not project_dir.is_dir():
        raise FileNotFoundError("Not a directory")

    q: queue.Queue[dict[str, Any]] = queue.Queue()

    def run_graph() -> None:
        _log.info(
            "SSE project migrate started project=%s max_repair=%s go_module=%r",
            project_rel,
            max_repair,
            go_module,
        )
        try:
            for node_id, out in stream_project_workflow(
                project_dir,
                max_repair_rounds=max_repair,
                go_module=go_module,
            ):
                q.put(
                    {
                        "type": "step",
                        "node": node_id,
                        "state": _serialize_project_state(out),
                    }
                )
            q.put({"type": "done"})
        except Exception as exc:  # noqa: BLE001
            _log.error("project migrate SSE failed", exc_info=True)
            q.put({"type": "error", "message": str(exc)})

    threading.Thread(target=run_graph, daemon=True).start()

    while True:
        item = q.get()
        yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        if item["type"] in {"done", "error"}:
            break


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/cases")
def list_cases() -> list[dict[str, str]]:
    return _discover_cases()


@app.post("/api/project/analyze")
def project_analyze(body: dict = Body(...)) -> dict[str, Any]:
    _log.info("POST /api/project/analyze project_dir=%r", (body or {}).get("project_dir"))
    try:
        rel = (body.get("project_dir") or "").replace("\\", "/").strip()
        if not rel:
            raise ValueError("project_dir required")
        project_dir = _resolve_project_dir(rel)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return analyze_project(project_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/project/migrate/stream")
def project_migrate_stream(
    project: str = Query(
        ...,
        description="Directory under project root, e.g. benchmark_dataset/tier1_basic/01_lru_cache",
    ),
    max_repair: int = Query(3, ge=1, le=20, description="Max repair rounds"),
    go_module: str | None = Query(None, description="Override go mod module path"),
) -> StreamingResponse:
    _log.info(
        "GET /api/project/migrate/stream project=%r max_repair=%s go_module=%r",
        project,
        max_repair,
        go_module,
    )

    def gen() -> Any:
        try:
            rel = project.replace("\\", "/").strip()
            yield from _sse_project_migrate(rel, max_repair, go_module)
        except FileNotFoundError as exc:
            payload = {"type": "error", "message": str(exc)}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            _log.error("project migrate stream failed", exc_info=True)
            payload = {"type": "error", "message": str(exc)}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/project/hitl/decide")
def project_hitl_decide(body: dict = Body(...)) -> dict[str, Any]:
    _log.info("POST /api/project/hitl/decide")
    thread_id = (body.get("thread_id") or "").strip()
    if not thread_id:
        raise HTTPException(status_code=400, detail="thread_id required")
    if not COMMAND_OK:
        return {"ok": False, "detail": "HITL resume not supported (Command unavailable)"}

    decision = body.get("decision")
    if body.get("key") and isinstance(decision, str):
        decision = {str(body.get("key")): decision}
    if decision is None:
        decision = "accept"

    steps: list[dict[str, Any]] = []
    try:
        for _node_id, out in resume_project_migrate(decision, thread_id):
            steps.append(_serialize_project_state(out))
    except Exception as exc:  # noqa: BLE001
        _log.error("HITL resume failed thread_id=%s", thread_id, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"ok": True, "steps": steps}
