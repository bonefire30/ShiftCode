# Testing Strategy

JAVA2GO testing should prove conversion behavior, explainability, and regression safety.

## Test Levels

- Unit tests: validate individual parser, transformer, generator, and reporter behavior.
- Conversion rule tests: validate Java input, expected Go output, status, warnings, and limitations for each rule.
- Integration tests: validate end-to-end conversion of small Java projects.
- Regression tests: lock fixes for previously broken cases.
- Fixture projects: validate behavior against realistic Java project structures.

## Conversion Test Shape

Each conversion test should define:

- Java input fixture
- Expected Go output or output fragment
- Expected status: success, warning, partial, unsupported, or error
- Expected warnings or errors
- Unsupported or manual follow-up notes

## Quality Gates

- New conversion rules should add or update tests.
- Bug fixes should add regression tests.
- Partial support should be tested as partial support, not treated as success.
- Unsupported features should produce understandable messages.
- Tests that would trigger LLM API calls or long-running model/API operations must not be run automatically by agents; provide the command for the user to run instead.

## Manual LLM Smoke Tests

The tier5 payment polymorphism smoke test is a manual evaluation gate for the
fixed LLM profiles. It must not run in routine unit tests or CI because it calls
real provider APIs unless `JAVA2GO_LLM_MOCK=1` is set.

The report's `model` field is the actual endpoint-accepted model identifier
used in the API request. These identifiers may differ from initial candidate
labels in planning documents. The currently verified identifiers are
`MiniMax-M2.7`, `deepseek-v4-flash`, and `GPT-5.3 Codex`.

Run it manually with:

```powershell
python scripts/run_tier5_three_profile_smoke.py
```

Acceptance for this smoke test:

- The report includes `minimax`, `deepseek`, and `codex-proxy` results.
- Each result has a non-empty `go_output_dir`.
- Each result has `llmCallStatus` set to `success`.
- Each result has `conversionStatus` set to `success`.
- Each result has `last_build_ok`, `last_test_ok`, `test_gen_ok`, and `test_quality_ok` set to true.
- Each result has `semantic_contract.ok` set to true for the fixture-specific payment contract.

The first-version semantic check uses source-structure checks, build/test
status, and generated-test quality. It does not append temporary semantic test
files to model output directories. The smoke report is evidence for this fixture
only. It does not prove full Java semantic equivalence or broad provider
support.

## Layered LLM Evaluation Suites

LLM evaluation is now layered so daily development does not depend on expensive
or slow full-project runs.

Suites are defined in `evaluation_suites/manifest.json`:

- `smoke`: 1-2 small fixtures for profile/API/report wiring. This validates the
  chain, not model quality.
- `core`: 3-5 representative fixtures for daily quality signal. Real LLM runs
  should usually compare `minimax` and `codex-proxy`; `deepseek` is not a default
  high-frequency profile.
- `features`: known-limitation fixtures for checked exceptions, generics,
  framework annotations, and stream pipelines. These fixtures must not hide
  unsupported or partial behavior as `success`.
- `wave1`: stage-gate full-project evaluation for release or model-decision
  points only. It is not a default debugging suite.

Default runs are mock-only:

```powershell
python scripts/run_layered_evaluation_suite.py --suite smoke
python scripts/run_layered_evaluation_suite.py --suite core
python scripts/run_layered_evaluation_suite.py --suite features
```

Real provider calls require an explicit profile and confirmation:

```powershell
python scripts/run_layered_evaluation_suite.py --suite smoke --profile codex-proxy --confirm-real-llm
python scripts/run_layered_evaluation_suite.py --suite core --profile minimax --confirm-real-llm
```

DeepSeek is disabled for non-smoke real runs unless explicitly enabled:

```powershell
$env:ALLOW_DEEPSEEK_EVALUATION=1
python scripts/run_layered_evaluation_suite.py --suite core --profile deepseek --confirm-real-llm
```

Every fixture entry must include `id`, `purpose`, `javaPattern`,
`expectedStatus`, and `mustNotReportSuccess`. Reports must include profile,
provider, model, latency/token usage when available, `llmCallStatus`, and
`conversionStatus`. Project-level runs should also include summary counts,
module/file conversion items where available, test/test-generation explanations,
and recommended next actions.

Mock reports validate manifest/report/status wiring only. They do not generate
Go output and do not require `go_output_dir`. Real LLM reports must include a
non-empty `go_output_dir` for generated outputs.

For real LLM layered runs, a fixture passes only when its observed
`conversionStatus` matches its manifest `expectedStatus`. Fixtures marked
`mustNotReportSuccess` cannot use `expectedStatus: success`.

## Failure Case Database

Track important failed or partial conversions using this format.

| Case | Status | Root Cause | Expected Behavior | Regression Test |
| --- | --- | --- | --- | --- |
| TBD | TBD | TBD | TBD | TBD |
