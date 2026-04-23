#!/usr/bin/env python3
"""
evaluate.py — run `go build` and `go test` for a benchmark case in a temp module.

Usage:
  python evaluate.py --case benchmark_dataset/tier2_oop/01_user_service
  python evaluate.py --case ... --code path/to/output.go
  python evaluate.py --case ... --use-golden   # uses golden_output.go as the candidate
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class EvalResult:
    case_name: str
    compile_ok: bool
    test_ok: bool
    build_stdout: str
    build_stderr: str
    test_stdout: str
    test_stderr: str
    lint_ok: bool | None
    lint_stdout: str
    lint_stderr: str
    repair_turns: int
    token_usage: int | None
    go_module: str

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    def to_markdown(self) -> str:
        return "\n".join(
            [
                f"## {self.case_name}",
                "",
                "| Metric | Value |",
                "|--------|-------|",
                f"| compile_ok | {self.compile_ok} |",
                f"| test_ok | {self.test_ok} |",
                f"| repair_turns | {self.repair_turns} |",
                f"| token_usage | {self.token_usage!s} |",
                f"| lint_ok | {self.lint_ok!s} |",
                f"| go_module | `{self.go_module}` |",
                "",
                "### go build (stderr if failed)",
                "```",
                (self.build_stderr or self.build_stdout)[:8000] or "(empty)",
                "```",
                "",
                "### go test (stderr/stdout if failed)",
                "```",
                (self.test_stderr or self.test_stdout)[:8000] or "(empty)",
                "```",
            ]
        )


def _run(
    args: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=True,
        env=env,
    )



def find_go() -> str | None:
    return shutil.which("go")


class GoToolchainError(RuntimeError):
    """Raised when the Go toolchain is missing or unusable."""


def evaluate_case(
    case_dir: Path,
    go_code: str,
    *,
    module_path: str = "example.com/bench",
    repair_turns: int = 0,
    token_usage: int | None = None,
    run_lint: bool = True,
) -> EvalResult:
    go = find_go()
    if not go:
        raise GoToolchainError(
            "`go` not found on PATH. Install Go and add it to PATH, then retry."
        )
    test_file = case_dir / "expected_test.go"
    if not test_file.is_file():
        raise FileNotFoundError(f"missing {test_file}")

    name = str(case_dir)

    with tempfile.TemporaryDirectory(prefix="goeval_") as td:
        root = Path(td)
        _run([go, "mod", "init", module_path], root)

        (root / "output.go").write_text(go_code, encoding="utf-8")
        shutil.copyfile(test_file, root / "expected_test.go")

        build = _run([go, "build", "./..."], root)
        compile_ok = build.returncode == 0

        test = _run([go, "test", "-v", "./..."], root)
        test_ok = test.returncode == 0

        lint_ok: bool | None = None
        lint_out = ""
        lint_err = ""
        if run_lint:
            golangci = shutil.which("golangci-lint")
            if golangci:
                lint = _run([golangci, "run", "./..."], root)
                lint_ok = lint.returncode == 0
                lint_out = lint.stdout
                lint_err = lint.stderr
            else:
                lint_ok = None
                lint_err = "(golangci-lint not in PATH, skipped)"

        return EvalResult(
            case_name=name,
            compile_ok=compile_ok,
            test_ok=test_ok,
            build_stdout=build.stdout,
            build_stderr=build.stderr,
            test_stdout=test.stdout,
            test_stderr=test.stderr,
            lint_ok=lint_ok,
            lint_stdout=lint_out,
            lint_stderr=lint_err,
            repair_turns=repair_turns,
            token_usage=token_usage,
            go_module=module_path,
        )


def main() -> None:
    ap = argparse.ArgumentParser(description="Run go build + go test for a benchmark case.")
    ap.add_argument(
        "--case",
        type=Path,
        default=Path("benchmark_dataset/tier2_oop/01_user_service"),
        help="Path to benchmark case directory (contains expected_test.go).",
    )
    ap.add_argument(
        "--code",
        type=Path,
        help="Path to Go source file to evaluate as output.go. Default: use --use-golden or stdin.",
    )
    ap.add_argument(
        "--use-golden",
        action="store_true",
        help="Use golden_output.go in the case dir as the candidate (for pipeline smoke test).",
    )
    ap.add_argument("--module", default="example.com/bench", help="go mod module path")
    ap.add_argument("--repair-turns", type=int, default=0, help="Recorded repair iterations")
    ap.add_argument("--token-usage", type=int, default=None, help="Optional token count for report")
    ap.add_argument("--no-lint", action="store_true", help="Do not run golangci-lint")
    ap.add_argument("--json", action="store_true", help="Print JSON result to stdout")
    ap.add_argument(
        "-o",
        "--output-report",
        type=Path,
        help="Write Markdown report to this file",
    )
    args = ap.parse_args()

    case_dir = args.case.resolve()
    if not case_dir.is_dir():
        sys.exit(f"error: case dir not found: {case_dir}")

    if args.use_golden:
        golden = case_dir / "golden_output.go"
        if not golden.is_file():
            sys.exit(f"error: {golden} not found; cannot --use-golden")
        go_code = golden.read_text(encoding="utf-8")
    elif args.code:
        go_code = args.code.read_text(encoding="utf-8")
    else:
        if sys.stdin.isatty():
            sys.exit(
                "error: provide --code path, --use-golden, or pipe Go source on stdin"
            )
        go_code = sys.stdin.read()

    try:
        result = evaluate_case(
            case_dir,
            go_code,
            module_path=args.module,
            repair_turns=args.repair_turns,
            token_usage=args.token_usage,
            run_lint=not args.no_lint,
        )
    except GoToolchainError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)

    if args.json:
        print(json.dumps(result.to_json(), indent=2, ensure_ascii=False))
    else:
        print(result.to_markdown())

    if args.output_report:
        args.output_report.write_text(result.to_markdown(), encoding="utf-8")
        print(f"\nWrote report to {args.output_report}", file=sys.stderr)

    # Exit 0 only if tests pass (compile is implied by test, but be explicit)
    if not result.compile_ok or not result.test_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
