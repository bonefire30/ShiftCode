"""
Manual three-profile smoke test for tier5 payment polymorphism.

This script calls real LLM APIs unless JAVA2GO_LLM_MOCK=1 is set. Do not run it
as part of routine unit tests or CI.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm_profiles import get_profile, validate_profile_runtime  # noqa: E402
from multi_agent_workflow import stream_project_workflow  # noqa: E402


FIXTURE = ROOT / "benchmark_dataset" / "tier5_polymorphism" / "01_payment_processor"
RUN_LOGS = ROOT / "run_logs"
PROFILES = ["minimax", "deepseek", "codex-proxy"]


def _rel(path: Path | str) -> str:
    p = Path(path).resolve()
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def _read_go_sources(go_output_dir: str) -> str:
    root = Path(go_output_dir)
    if not root.is_dir():
        return ""
    parts: list[str] = []
    for path in sorted(root.rglob("*.go")):
        if path.name.endswith("_test.go"):
            continue
        parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n\n".join(parts)


def _semantic_contract(go_source: str) -> dict[str, Any]:
    checks = {
        "has_payment_interface_or_contract": bool(re.search(r"type\s+Payment\s+interface|interface\s*{[^}]*Process\(\)\s+string", go_source, re.S)),
        "has_credit_card_payment": "CreditCardPayment" in go_source,
        "has_paypal_payment": "PaypalPayment" in go_source,
        "credit_process_returns_credit": bool(re.search(r"func\s*\([^)]*CreditCardPayment[^)]*\)\s*Process\(\)\s*string\s*{[^}]*\"credit\"", go_source, re.S)),
        "paypal_process_returns_paypal": bool(re.search(r"func\s*\([^)]*PaypalPayment[^)]*\)\s*Process\(\)\s*string\s*{[^}]*\"paypal\"", go_source, re.S)),
        "run_payment_dispatches_process": bool(re.search(r"func\s+RunPayment\s*\([^)]*\).*{[^}]*\.Process\(\)", go_source, re.S)),
        "log_transaction_exists": "LogTransaction" in go_source,
        "id_exposed_or_getter_exists": bool(re.search(r"\bId\s+int\b|GetId\s*\(\)\s*int", go_source)),
    }
    return {"ok": all(checks.values()), "checks": checks}


def _run_profile(profile_name: str, max_repair: int) -> dict[str, Any]:
    profile = get_profile(profile_name)
    validate_profile_runtime(profile)
    started = time.time()
    final_node = ""
    final_state: dict[str, Any] = {}
    error = ""
    try:
        for node_id, out in stream_project_workflow(
            FIXTURE,
            max_repair_rounds=max_repair,
            go_module=None,
            llm_profile=profile.profile,
        ):
            final_node = str(node_id)
            final_state.update(dict(out or {}))
    except Exception as exc:  # noqa: BLE001
        error = f"{exc.__class__.__name__}: {exc}"

    go_output_dir = str(final_state.get("go_output_dir") or "")
    semantic = _semantic_contract(_read_go_sources(go_output_dir))
    llm_meta = dict(final_state.get("llm_run_metadata") or {})
    conversion_status = str(llm_meta.get("conversionStatus") or ("error" if error else "partial"))
    llm_call_status = str(llm_meta.get("llmCallStatus") or ("error" if error else "unknown"))
    passed = (
        not error
        and bool(final_state.get("last_build_ok"))
        and bool(final_state.get("last_test_ok"))
        and bool(final_state.get("test_gen_ok"))
        and bool(final_state.get("test_quality_ok"))
        and semantic["ok"]
    )
    return {
        "profile": profile.profile,
        "provider": profile.provider,
        "model": profile.model,
        "duration_s": round(time.time() - started, 3),
        "status": "passed" if passed else "failed",
        "final_node": final_node,
        "error": error,
        "go_output_dir": _rel(go_output_dir) if go_output_dir else "",
        "last_build_ok": bool(final_state.get("last_build_ok", False)),
        "last_test_ok": bool(final_state.get("last_test_ok", False)),
        "test_gen_ok": bool(final_state.get("test_gen_ok", False)),
        "test_quality_ok": bool(final_state.get("test_quality_ok", False)),
        "conversionStatus": conversion_status,
        "llmCallStatus": llm_call_status,
        "llm_run_metadata": llm_meta,
        "semantic_contract": semantic,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run tier5 payment processor smoke test across LLM profiles")
    parser.add_argument("--profile", choices=PROFILES, action="append", help="Profile to run; repeatable. Defaults to all three.")
    parser.add_argument("--max-repair", type=int, default=3)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    selected = args.profile or PROFILES
    started_at = datetime.now().astimezone()
    results = [_run_profile(profile, args.max_repair) for profile in selected]
    passed = sum(1 for r in results if r["status"] == "passed")
    report = {
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now().astimezone().isoformat(),
        "fixture": _rel(FIXTURE),
        "profiles": selected,
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }
    output = args.output or RUN_LOGS / f"tier5_three_profile_smoke_{started_at.strftime('%Y%m%d_%H%M%S')}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for result in results:
        print(
            f"{result['profile']}: {result['status']} build={result['last_build_ok']} "
            f"test={result['last_test_ok']} semantic={result['semantic_contract']['ok']} output={result['go_output_dir']}"
        )
    print(f"Saved report to {_rel(output)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
