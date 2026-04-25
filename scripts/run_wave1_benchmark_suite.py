"""
Run all benchmark_projects/wave1 multi-file cases serially and write a JSON report.

Usage:
  python scripts/run_wave1_benchmark_suite.py
  python scripts/run_wave1_benchmark_suite.py --max-repair 2
  python scripts/run_wave1_benchmark_suite.py --case 01_layered_crud_service
  python scripts/run_wave1_benchmark_suite.py --list-only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from multi_agent_workflow import stream_project_workflow  # noqa: E402


BENCHMARK_ROOT = ROOT / "benchmark_projects" / "wave1"
RUN_LOGS = ROOT / "run_logs"


def _find_cases() -> list[Path]:
    cases = sorted({p.parent.resolve() for p in BENCHMARK_ROOT.rglob("migration_prompt.txt")})
    return [p for p in cases if p.is_dir()]


def _filter_cases(cases: list[Path], case_filter: str) -> list[Path]:
    needle = case_filter.strip().replace("\\", "/").lower()
    if not needle:
        return cases
    matched: list[Path] = []
    for case in cases:
        rel = _rel_path(case).lower()
        name = case.name.lower()
        if needle == name or needle == rel or needle in rel:
            matched.append(case)
    return matched


def _rel_path(path: Path) -> str:
    path = path.resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _short_status(result: dict[str, Any]) -> str:
    return "PASS" if result["status"] == "passed" else "FAIL"


def _tail_text(value: Any, limit: int = 3000) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[-limit:]


def _derive_status(final_state: dict[str, Any]) -> str:
    if str(final_state.get("fatal") or "").strip():
        return "failed"
    if bool(final_state.get("last_build_ok")) and bool(final_state.get("last_test_ok")):
        if bool(final_state.get("test_gen_ok")) and bool(final_state.get("test_quality_ok")):
            return "passed"
    return "failed"


def _run_one_case(case_dir: Path, *, max_repair_rounds: int) -> dict[str, Any]:
    started = time.time()
    final_node = ""
    final_state: dict[str, Any] = {}
    error = ""

    try:
        for node_id, out in stream_project_workflow(
            case_dir,
            max_repair_rounds=max_repair_rounds,
            go_module=None,
        ):
            final_node = str(node_id)
            final_state = dict(out or {})
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"

    status = "failed" if error else _derive_status(final_state)
    build_log = str(final_state.get("last_build_log") or "")
    modules = final_state.get("modules") if isinstance(final_state.get("modules"), list) else []
    java_files = final_state.get("java_files") if isinstance(final_state.get("java_files"), list) else []

    return {
        "case": _rel_path(case_dir),
        "status": status,
        "duration_s": round(time.time() - started, 3),
        "final_node": final_node,
        "thread_id": str(final_state.get("thread_id") or ""),
        "fatal": str(final_state.get("fatal") or ""),
        "exception": error,
        "last_build_ok": bool(final_state.get("last_build_ok", False)),
        "last_test_ok": bool(final_state.get("last_test_ok", False)),
        "test_gen_ok": bool(final_state.get("test_gen_ok", False)),
        "test_quality_ok": bool(final_state.get("test_quality_ok", False)),
        "expected_tests": int(final_state.get("test_gen_expected_count") or 0),
        "generated_tests": int(final_state.get("test_gen_generated_count") or 0),
        "repair_round": int(final_state.get("repair_round") or 0),
        "java_file_count": len(java_files),
        "module_count": len(modules),
        "module_layer_count": int(final_state.get("module_layer_count") or 0),
        "go_output_dir": str(final_state.get("go_output_dir") or ""),
        "test_gen_failures": list(final_state.get("test_gen_failures") or []),
        "test_gen_warnings": list(final_state.get("test_gen_warnings") or []),
        "last_build_log_tail": _tail_text(build_log),
    }


def _print_case_line(index: int, total: int, result: dict[str, Any]) -> None:
    build = "OK" if result["last_build_ok"] else "FAIL"
    test = "OK" if result["last_test_ok"] else "FAIL"
    print(
        f"[{index}/{total}] {result['case']:<62} {_short_status(result):<4} "
        f"files={result['java_file_count']} modules={result['module_count']} "
        f"tests={result['generated_tests']}/{result['expected_tests']} "
        f"build={build} test={test} repairs={result['repair_round']} "
        f"duration={result['duration_s']:.3f}s"
    )
    if result["status"] != "passed":
        reason = result["fatal"] or result["exception"] or "; ".join(result["test_gen_failures"][:2])
        if reason:
            print(f"      reason: {reason}")


def _write_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run wave1 multi-file benchmark suite")
    parser.add_argument("--max-repair", type=int, default=3, help="Max repair rounds per case")
    parser.add_argument(
        "--case",
        default="",
        help="Run only matching case name/path, e.g. 01_layered_crud_service",
    )
    parser.add_argument("--list-only", action="store_true", help="List discovered cases and exit")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON report path; defaults to run_logs/wave1_benchmark_suite_<timestamp>.json",
    )
    args = parser.parse_args()

    cases = _find_cases()
    if args.case:
        cases = _filter_cases(cases, args.case)
    if not cases:
        suffix = f" matching {args.case!r}" if args.case else ""
        print(f"No wave1 benchmark cases found under {BENCHMARK_ROOT}{suffix}", file=sys.stderr)
        return 1

    if args.list_only:
        for case in cases:
            print(_rel_path(case))
        return 0

    started_at = datetime.now().astimezone()
    ts = started_at.strftime("%Y%m%d_%H%M%S")
    output_path = args.output or (RUN_LOGS / f"wave1_benchmark_suite_{ts}.json")

    print(f"Discovered {len(cases)} wave1 benchmark cases under {_rel_path(BENCHMARK_ROOT)}")
    print(f"JSON report: {_rel_path(output_path)}")

    results: list[dict[str, Any]] = []
    for idx, case_dir in enumerate(cases, 1):
        result = _run_one_case(case_dir, max_repair_rounds=args.max_repair)
        results.append(result)
        _print_case_line(idx, len(cases), result)

    finished_at = datetime.now().astimezone()
    passed = sum(1 for r in results if r["status"] == "passed")
    failed = len(results) - passed
    report = {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_s": round((finished_at - started_at).total_seconds(), 3),
        "benchmark_root": _rel_path(BENCHMARK_ROOT),
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "max_repair_rounds": int(args.max_repair),
        "results": results,
    }
    _write_report(report, output_path)

    print(f"SUMMARY: total={len(results)} passed={passed} failed={failed}")
    print(f"Saved JSON report to {_rel_path(output_path)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
