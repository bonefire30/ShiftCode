"""
Run layered JAVA2GO LLM evaluation suites.

Default mode is mock-only metadata validation. Real LLM calls require an explicit
profile and --confirm-real-llm. Wave1 is a stage-gate suite and is never a
default daily run.
"""

from __future__ import annotations

import argparse
import json
import os
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


MANIFEST_PATH = ROOT / "evaluation_suites" / "manifest.json"
RUN_LOGS = ROOT / "run_logs"
VALID_STATUSES = {"success", "warning", "partial", "unsupported", "error"}
VALID_REAL_PROFILES = {"minimax", "deepseek", "codex-proxy"}
REQUIRED_SUITES = {"smoke", "core", "features", "wave1", "parser-config", "exception-flow"}
REQUIRED_FIXTURE_KEYS = {"id", "path", "purpose", "javaPattern", "expectedStatus", "mustNotReportSuccess"}


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> None:
    suites = manifest.get("suites")
    if not isinstance(suites, dict):
        raise ValueError("manifest.suites must be an object")
    missing = REQUIRED_SUITES - set(suites)
    if missing:
        raise ValueError(f"manifest missing required suites: {', '.join(sorted(missing))}")
    fixture_ids: set[str] = set()
    for suite_name, suite_data_raw in suites.items():
        if not isinstance(suite_data_raw, dict):
            raise ValueError(f"suite {suite_name!r} must be an object")
        suite_data = suite_data_raw
        allow_profiles = suite_data.get("allowRealProfiles") or []
        if not isinstance(allow_profiles, list) or any(p not in VALID_REAL_PROFILES for p in allow_profiles):
            raise ValueError(f"suite {suite_name!r} has invalid allowRealProfiles")
        fixtures = suite_data.get("fixtures") or []
        if not isinstance(fixtures, list) or not fixtures:
            raise ValueError(f"suite {suite_name!r} must define at least one fixture")
        if suite_name == "smoke" and not (1 <= len(fixtures) <= 2):
            raise ValueError("smoke suite must contain 1 to 2 fixtures")
        if suite_name == "core" and not (3 <= len(fixtures) <= 5):
            raise ValueError("core suite must contain 3 to 5 fixtures")
        for fixture in fixtures:
            if not isinstance(fixture, dict):
                raise ValueError(f"suite {suite_name!r} has a non-object fixture")
            missing_keys = REQUIRED_FIXTURE_KEYS - set(fixture)
            if missing_keys:
                raise ValueError(f"fixture in suite {suite_name!r} missing keys: {', '.join(sorted(missing_keys))}")
            fixture_id = str(fixture.get("id") or "")
            if fixture_id in fixture_ids:
                raise ValueError(f"duplicate fixture id: {fixture_id}")
            fixture_ids.add(fixture_id)
            if not fixture_id.startswith(suite_name + "."):
                raise ValueError(f"fixture id {fixture_id!r} must start with {suite_name!r}.")
            fixture_path = ROOT / str(fixture.get("path") or "")
            if not fixture_path.exists():
                raise ValueError(f"fixture path does not exist: {fixture.get('path')}")
            expected = str(fixture.get("expectedStatus") or "")
            if expected not in VALID_STATUSES:
                raise ValueError(f"fixture {fixture_id!r} has invalid expectedStatus: {expected!r}")
            if not isinstance(fixture.get("mustNotReportSuccess"), bool):
                raise ValueError(f"fixture {fixture_id!r} mustNotReportSuccess must be boolean")
            if fixture.get("mustNotReportSuccess") and expected == "success":
                raise ValueError(f"fixture {fixture_id!r} cannot expect success when mustNotReportSuccess is true")


def suite_names(manifest: dict[str, Any]) -> list[str]:
    suites = manifest.get("suites") or {}
    return sorted(str(name) for name in suites)


def _rel(path: Path | str) -> str:
    p = Path(path).resolve()
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def _conversion_status_from_fixture(fixture: dict[str, Any]) -> str:
    expected = str(fixture.get("expectedStatus") or "partial")
    if expected not in VALID_STATUSES:
        raise ValueError(f"invalid expectedStatus: {expected!r}")
    return expected


def _mock_fixture_result(suite: str, fixture: dict[str, Any], profile: str) -> dict[str, Any]:
    expected_status = _conversion_status_from_fixture(fixture)
    must_not_success = bool(fixture.get("mustNotReportSuccess"))
    status_ok = not (must_not_success and expected_status == "success")
    return {
        "suite": suite,
        "fixture_id": fixture.get("id"),
        "fixture_path": fixture.get("path"),
        "purpose": fixture.get("purpose"),
        "javaPattern": fixture.get("javaPattern"),
        "expectedStatus": fixture.get("expectedStatus"),
        "mustNotReportSuccess": must_not_success,
        "profile": profile,
        "provider": "mock",
        "model": "mock",
        "status": "passed" if status_ok else "failed",
        "duration_s": 0,
        "go_output_dir": "",
        "llmCallStatus": "success",
        "conversionStatus": expected_status,
        "last_build_ok": None,
        "last_test_ok": None,
        "test_gen_ok": None,
        "test_quality_ok": None,
        "llm_run_metadata": {
            "profile": profile,
            "provider": "mock",
            "model": "mock",
            "llmCallStatus": "success",
            "conversionStatus": expected_status,
            "promptVersion": "project-migration-v1",
            "tokenUsage": {
                "promptTokens": None,
                "completionTokens": None,
                "totalTokens": None,
            },
            "error": None,
        },
    }


def _real_fixture_result(suite: str, fixture: dict[str, Any], profile_name: str, max_repair: int) -> dict[str, Any]:
    profile = get_profile(profile_name)
    validate_profile_runtime(profile)
    fixture_path = ROOT / str(fixture.get("path") or "")
    started = time.time()
    final_node = ""
    final_state: dict[str, Any] = {}
    error = ""
    try:
        for node_id, out in stream_project_workflow(
            fixture_path,
            max_repair_rounds=max_repair,
            go_module=None,
            llm_profile=profile.profile,
        ):
            final_node = str(node_id)
            final_state.update(dict(out or {}))
    except Exception as exc:  # noqa: BLE001
        error = f"{exc.__class__.__name__}: {exc}"

    llm_meta = dict(final_state.get("llm_run_metadata") or {})
    conversion_status = str(llm_meta.get("conversionStatus") or ("error" if error else "partial"))
    llm_call_status = str(llm_meta.get("llmCallStatus") or ("error" if error else "unknown"))
    must_not_success = bool(fixture.get("mustNotReportSuccess"))
    expected_status = _conversion_status_from_fixture(fixture)
    status_ok = not error and llm_call_status == "success" and conversion_status == expected_status
    gate_failures: list[str] = []
    if conversion_status != expected_status:
        gate_failures.append(f"expected conversionStatus {expected_status}, got {conversion_status}")
    if must_not_success and conversion_status == "success":
        gate_failures.append("mustNotReportSuccess=true but observed conversionStatus success")
    if must_not_success and conversion_status == "success":
        status_ok = False

    return {
        "suite": suite,
        "fixture_id": fixture.get("id"),
        "fixture_path": fixture.get("path"),
        "purpose": fixture.get("purpose"),
        "javaPattern": fixture.get("javaPattern"),
        "expectedStatus": fixture.get("expectedStatus"),
        "mustNotReportSuccess": must_not_success,
        "profile": profile.profile,
        "provider": profile.provider,
        "model": profile.model,
        "status": "passed" if status_ok else "failed",
        "duration_s": round(time.time() - started, 3),
        "final_node": final_node,
        "error": error,
        "go_output_dir": _rel(str(final_state.get("go_output_dir") or "")) if final_state.get("go_output_dir") else "",
        "llmCallStatus": llm_call_status,
        "conversionStatus": conversion_status,
        "gateFailures": gate_failures,
        "last_build_ok": bool(final_state.get("last_build_ok", False)),
        "last_test_ok": bool(final_state.get("last_test_ok", False)),
        "test_gen_ok": bool(final_state.get("test_gen_ok", False)),
        "test_quality_ok": bool(final_state.get("test_quality_ok", False)),
        "llm_run_metadata": llm_meta,
        "projectStatusSummary": llm_meta.get("projectStatusSummary"),
        "summaryCompleteness": llm_meta.get("summaryCompleteness"),
        "conversionItems": llm_meta.get("conversionItems"),
        "testFailureExplanations": llm_meta.get("testFailureExplanations"),
        "testGenerationReasons": llm_meta.get("testGenerationReasons"),
        "testIssueCategories": llm_meta.get("testIssueCategories"),
        "recommendedNextActions": llm_meta.get("recommendedNextActions"),
    }


def run_suite(
    *,
    suite: str,
    profile: str,
    confirm_real_llm: bool,
    max_repair: int = 3,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = manifest or load_manifest()
    suites = manifest.get("suites") or {}
    if suite not in suites:
        allowed = ", ".join(suite_names(manifest))
        raise ValueError(f"unknown suite {suite!r}; expected one of: {allowed}")
    suite_data = dict(suites[suite])
    fixtures = list(suite_data.get("fixtures") or [])
    started_at = datetime.now().astimezone()
    is_mock = profile == "mock"
    if not is_mock and not confirm_real_llm:
        raise RuntimeError("real LLM evaluation requires --confirm-real-llm")
    if not is_mock:
        allowed_profiles = suite_data.get("allowRealProfiles") or []
        if profile not in allowed_profiles:
            raise RuntimeError(f"profile {profile!r} is not allowed for suite {suite!r}")

    results = [
        _mock_fixture_result(suite, fixture, profile)
        if is_mock
        else _real_fixture_result(suite, fixture, profile, max_repair)
        for fixture in fixtures
    ]
    passed = sum(1 for result in results if result.get("status") == "passed")
    return {
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now().astimezone().isoformat(),
        "suite": suite,
        "suite_purpose": suite_data.get("purpose"),
        "profile": profile,
        "mode": "mock" if is_mock else "real-llm",
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }


def main() -> int:
    manifest = load_manifest()
    parser = argparse.ArgumentParser(description="Run layered JAVA2GO LLM evaluation suite")
    parser.add_argument("--suite", choices=suite_names(manifest), default="smoke")
    parser.add_argument("--profile", default="mock", help="mock, minimax, deepseek, or codex-proxy")
    parser.add_argument("--confirm-real-llm", action="store_true", help="Required for real provider API calls")
    parser.add_argument("--max-repair", type=int, default=3)
    parser.add_argument("--list-suites", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    if args.list_suites:
        for name in suite_names(manifest):
            print(name)
        return 0

    if args.profile != "mock":
        get_profile(args.profile)
    if args.profile == "deepseek" and args.suite != "smoke" and not os.environ.get("ALLOW_DEEPSEEK_EVALUATION"):
        raise RuntimeError("DeepSeek is disabled for non-smoke runs unless ALLOW_DEEPSEEK_EVALUATION=1")

    report = run_suite(
        suite=args.suite,
        profile=args.profile,
        confirm_real_llm=args.confirm_real_llm,
        max_repair=args.max_repair,
        manifest=manifest,
    )
    ts = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    output = args.output or RUN_LOGS / f"layered_eval_{args.suite}_{args.profile}_{ts}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for result in report["results"]:
        print(
            f"{result['fixture_id']}: {result['status']} profile={result['profile']} "
            f"llm={result['llmCallStatus']} conversion={result['conversionStatus']}"
        )
        if result.get("gateFailures"):
            print("  gateFailures: " + "; ".join(str(x) for x in result["gateFailures"]))
    print(f"Saved report to {_rel(output)}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
