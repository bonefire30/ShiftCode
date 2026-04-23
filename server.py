"""
FastAPI + SSE for multi-agent migration workflow progress.

Run: uvicorn server:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from logging_config import setup_logging
from multi_agent_workflow import (
    COMMAND_OK,
    Command,
    analyze_project,
    resume_project_migrate,
    stream_project_workflow,
)
from workflow import stream_workflow

setup_logging()
_log = logging.getLogger("shiftcode.server")

ROOT = Path(__file__).resolve().parent

app = FastAPI(title="ShiftCode Migration API", version="0.1.0")

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
    """JSON-safe subset for project migration SSE (avoid huge blobs)."""
    out: dict[str, Any] = {}
    for k, v in state.items():
        if k == "java_infos" and isinstance(v, dict):
            jm: dict[str, Any] = {}
            for p, d in v.items():
                if isinstance(d, dict):
                    d2 = {**d, "source_text": (d.get("source_text") or "")[:2000]}
                    jm[p] = d2
            out["java_infos"] = jm
        elif k == "file_states" and isinstance(v, dict):
            fs_out: dict[str, Any] = {}
            for p, fs in v.items():
                if isinstance(fs, dict):
                    gc = str(fs.get("go_code") or "")
                    fs_out[p] = {
                        **fs,
                        "go_code": gc[:2000] + ("…" if len(gc) > 2000 else ""),
                    }
                else:
                    fs_out[p] = str(fs)[:200]
            out["file_states"] = fs_out
        elif k in ("thread_id", "fatal", "go_module", "go_output_dir", "project_dir"):
            out[k] = v
        elif k in ("translation_batches", "framework_flags", "java_files", "dependency_graph"):
            out[k] = v
        elif k == "last_build_log" and isinstance(v, str):
            out[k] = v[:8000] if v else v
        elif k == "symbol_table_data" and isinstance(v, dict):
            out[k] = v  # may be large; UI can handle
        elif k in (
            "current_batch_idx",
            "repair_round",
            "max_repair_rounds",
            "total_tokens",
            "last_build_ok",
            "last_test_ok",
        ):
            out[k] = v
        elif k == "hitl_decisions" and isinstance(v, dict):
            out[k] = v
        elif isinstance(v, (bool, int, float, str)) or v is None:
            out[k] = v
        elif isinstance(v, dict):
            out[k] = v
    return out


def _serialize_state(state: dict[str, Any]) -> dict[str, Any]:
    """Make graph state JSON-serializable for SSE."""
    out: dict[str, Any] = {}
    for k, v in state.items():
        if k in (
            "java_source",
            "go_code",
            "last_repair_error",
            "build_log",
            "test_log",
        ):
            out[k] = v if isinstance(v, str) else str(v) if v is not None else ""
        elif k == "messages" and isinstance(v, list):
            n = len(v)
            # Agent inner-loop steps can be long; keep a larger tail for SSE UI
            _tail = 24
            if n > _tail:
                out["messages"] = v[-_tail:]
            else:
                out["messages"] = v
            out["messages_count"] = n
        elif k == "workspace_dir":
            out[k] = (v or "") if isinstance(v, str) else str(v)
        elif k == "last_eval" and isinstance(v, dict):
            out[k] = v
        elif isinstance(v, (bool, int, float, str)) or v is None:
            out[k] = v
        elif isinstance(v, dict):
            out[k] = v
        else:
            out[k] = str(v)
    return out


def _discover_cases() -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    for p in sorted(ROOT.glob("benchmark_dataset/**/source.java")):
        rel = p.parent.relative_to(ROOT)
        path_str = str(rel).replace("\\", "/")
        cases.append(
            {
                "id": path_str,
                "name": p.parent.name,
                "path": path_str,
            }
        )
    return cases


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/cases")
def list_cases() -> list[dict[str, str]]:
    return _discover_cases()


@app.get("/api/case/source")
def get_case_source(
    case: str = Query(
        ...,
        description="Case directory or path under project, e.g. benchmark_dataset/tier2_oop/01_user_service",
    ),
) -> dict[str, str]:
    """Read source.java for preview before running migration (fixes empty Java panel during streaming)."""
    try:
        case_dir = _resolve_case_dir(case)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    p = case_dir / "source.java"
    if not p.is_file():
        raise HTTPException(status_code=404, detail="source.java not found")
    try:
        content = p.read_text(encoding="utf-8")
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    rel = case_dir.relative_to(ROOT)
    return {
        "path": str(rel).replace("\\", "/"),
        "content": content,
    }


def _resolve_case_dir(case_path: str) -> Path:
    """Return directory that contains source.java. Paths must stay under project root."""
    root_resolved = ROOT.resolve()
    raw = (ROOT / case_path).resolve()
    if not str(raw).startswith(str(root_resolved)):
        raise FileNotFoundError("Invalid case path (outside project)")
    if raw.is_file() and raw.name == "source.java":
        return raw.parent
    if raw.is_dir() and (raw / "source.java").is_file():
        return raw
    raise FileNotFoundError(f"Case not found or missing source.java: {case_path}")


import queue
import threading
from langchain_core.callbacks import BaseCallbackHandler

class StreamingCallback(BaseCallbackHandler):
    def __init__(self, q: queue.Queue):
        self.q = q
    
    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.q.put({"type": "chunk", "content": token})

    def on_agent_intermediate(self, state: dict[str, Any]) -> None:
        """
        Pushed from workflow._agent_translator_node during the tool loop
        (between graph-level translator/qa steps).
        """
        self.q.put(
            {
                "type": "step",
                "node": "translator_internal",
                "state": _serialize_state(state),
            }
        )


def _sse_migrate(
    case_path: str,
    use_stub: bool,
    max_calls: int,
    use_legacy: bool = False,
) -> Any:
    case_dir = _resolve_case_dir(case_path)
    
    q = queue.Queue()

    def run_graph():
        try:
            for node_id, state in stream_workflow(
                case_dir,
                use_stub=use_stub,
                max_translator_calls=max_calls,
                use_legacy_translator=use_legacy,
                callbacks=[StreamingCallback(q)] if (not use_stub and not use_legacy) else None,
            ):
                q.put({
                    "type": "step",
                    "node": node_id,
                    "state": _serialize_state(state),
                })
            q.put({"type": "done"})
        except Exception as e:
            q.put({"type": "error", "message": str(e)})

    threading.Thread(target=run_graph, daemon=True).start()

    while True:
        item = q.get()
        yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        if item["type"] in ("done", "error"):
            break


@app.get("/api/migrate/stream")
def migrate_stream(
    case: str = Query(
        ..., description="Path under project root, e.g. benchmark_dataset/tier2_oop/01_user_service"
    ),
    use_stub: bool = Query(False, description="Use golden_output.go, no LLM"),
    max_calls: int = Query(3, ge=1, le=20, description="Max translator invocations"),
    use_legacy: bool = Query(
        False,
        description="If true, one-shot fenced-Go output (MIGRATION_USE_AGENT=0). If false, file-tool agent.",
    ),
) -> StreamingResponse:
    """SSE stream: each event is a JSON with type step|done|error."""

    def gen():
        try:
            yield from _sse_migrate(case, use_stub, max_calls, use_legacy)
        except FileNotFoundError as e:
            err = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            err = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _resolve_project_dir(path: str) -> Path:
    root_resolved = ROOT.resolve()
    raw = (ROOT / path).resolve()
    if not str(raw).startswith(str(root_resolved)):
        raise FileNotFoundError("Invalid project path (outside project root)")
    if not raw.is_dir():
        raise FileNotFoundError(f"Not a directory: {path!r}")
    return raw


@app.post("/api/project/analyze")
def project_analyze(body: dict = Body(...)) -> dict:
    _log.info("POST /api/project/analyze project_dir=%r", (body or {}).get("project_dir"))
    try:
        rel = (body.get("project_dir") or "").replace("\\", "/").strip()
        if not rel:
            raise ValueError("project_dir required")
        p = _resolve_project_dir(rel)
    except (FileNotFoundError, ValueError) as e:
        _log.warning("project_analyze 400: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        out = analyze_project(p)
        _log.info("project_analyze 成功 project=%s", p)
        return out
    except FileNotFoundError as e:
        _log.warning("project_analyze 404: %s", e)
        raise HTTPException(status_code=404, detail=str(e)) from e


def _sse_project_migrate(
    project_rel: str, max_repair: int, go_module: str | None
) -> Any:
    pr = (ROOT / project_rel).resolve()
    rroot = ROOT.resolve()
    if not str(pr).startswith(str(rroot)):
        raise FileNotFoundError("Invalid path")
    if not pr.is_dir():
        raise FileNotFoundError("Not a directory")

    q: queue.Queue = queue.Queue()

    def run_g():
        _log.info("SSE 任务启动 project=%s max_repair=%s", project_rel, max_repair)
        try:
            for node_id, out in stream_project_workflow(
                pr, max_repair_rounds=max_repair, go_module=go_module
            ):
                _log.info("SSE step node=%s", node_id)
                q.put(
                    {
                        "type": "step",
                        "node": node_id,
                        "state": _serialize_project_state(out),
                    }
                )
            _log.info("SSE 任务完成 project=%s", project_rel)
            q.put({"type": "done"})
        except Exception as e:  # noqa: BLE001
            _log.error("SSE 任务异常 project=%s", project_rel, exc_info=True)
            q.put({"type": "error", "message": str(e)})

    threading.Thread(target=run_g, daemon=True).start()
    while True:
        item = q.get()
        yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        if item["type"] in ("done", "error"):
            break


@app.get("/api/project/migrate/stream")
def project_migrate_stream(
    project: str = Query(
        ..., description="Directory under project root, e.g. benchmark_dataset/tier1_basic/01_lru_cache"
    ),
    max_repair: int = Query(3, ge=1, le=20, description="Max repair rounds per failed build"),
    go_module: str | None = Query(
        None, description="Override go mod module path (e.g. m.example/proj)"
    ),
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
        except FileNotFoundError as e:
            _log.warning("project_migrate_stream: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            _log.error("project_migrate_stream 异常", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

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
def project_hitl_decide(body: dict = Body(...)) -> dict:
    _log.info("POST /api/project/hitl/decide")
    tid = (body.get("thread_id") or "").strip()
    if not tid:
        raise HTTPException(status_code=400, detail="thread_id required")
    if not COMMAND_OK or Command is None:
        return {"ok": False, "detail": "HITL resume not supported (Command unavailable)"}
    decision = body.get("decision")
    if body.get("key") and isinstance(decision, str):
        decision = {str(body.get("key")): decision}
    if decision is None:
        decision = "accept"
    out_list: list[dict[str, Any]] = []
    try:
        for _nid, o in resume_project_migrate(decision, tid):
            _log.info("HITL resume 步 output_keys=%s", list(o.keys()) if isinstance(o, dict) else type(o))
            out_list.append(_serialize_project_state(o))
    except Exception as e:  # noqa: BLE001
        _log.error("HITL resume 失败 thread_id=%s", tid, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
    _log.info("HITL resume 成功 steps=%d", len(out_list))
    return {"ok": True, "steps": out_list}
