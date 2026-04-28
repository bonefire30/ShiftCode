# LLM Evaluation Acceptance Record

This record captures the first accepted quality gate for the fixed JAVA2GO LLM
evaluation profiles.

## Scope

- Profiles: `minimax`, `deepseek`, and `codex-proxy`.
- Fixture: `benchmark_dataset/tier5_polymorphism/01_payment_processor`.
- Validation level: smoke-level semantic signal, not full Java semantic
  equivalence proof.

## Verified Model Identifiers

The `model` field records the actual endpoint-accepted model identifier sent in
API requests.

| Profile | Provider | Model |
| --- | --- | --- |
| `minimax` | `minimax` | `MiniMax-M2.7` |
| `deepseek` | `deepseek` | `deepseek-v4-flash` |
| `codex-proxy` | `openai-compatible` | `GPT-5.3 Codex` |

## Automated Verification

The release candidate passed:

```powershell
python -m unittest discover -s tests
python -m py_compile llm_profiles.py workflow.py multi_agent_workflow.py server.py logging_config.py security.py scripts/run_tier5_three_profile_smoke.py
git diff --check
```

The unit test run reported:

```text
Ran 31 tests in 0.202s
OK
```

`git diff --check` reported only Windows LF/CRLF warnings and no whitespace
errors.

## Manual Smoke Evidence

Final local smoke report:

```text
run_logs/tier5_three_profile_smoke_20260426_163606.json
```

The report showed:

- `passed: 3`
- `failed: 0`
- All three profiles had non-empty `go_output_dir` values.
- All three profiles had `llmCallStatus: success`.
- All three profiles had `conversionStatus: success`.
- All three profiles had `last_build_ok`, `last_test_ok`, `test_gen_ok`, and
  `test_quality_ok` set to true.
- All three profiles had `semantic_contract.ok: true`.

## Semantic Smoke Contract

The first-version tier5 smoke gate checks source structure, build/test status,
and generated-test quality. It does not append temporary semantic test files to
model output directories.

The fixture-specific checks include:

- Payment interface or equivalent contract exists.
- Credit card and PayPal payment types exist.
- Credit card `Process()` returns `"credit"`.
- PayPal `Process()` returns `"paypal"`.
- `RunPayment` dispatches through `Process()`.
- `LogTransaction` exists.
- ID is exposed or readable through a getter.

## Known Limits

- These profiles are evaluation candidates, not a general LLM gateway.
- The smoke result is evidence for one fixture only.
- Smoke pass does not prove complete Java semantic equivalence.
- Provider token usage may be missing; missing values are reported as
  null/unknown, not estimated.

## Next Gate: Layered Suite Acceptance

Before using wave1 as a model-quality decision input, quality review should
accept the layered suite manifest in `evaluation_suites/manifest.json`.

The intended order is:

1. Verify profile/API/report wiring with `smoke`.
2. Use `core` for daily small-sample model quality checks.
3. Use `features` to ensure known unsupported or partial Java features are not
   hidden as `success`.
4. Use `wave1` only at release or model-decision points.

Default layered suite runs are mock-only. Real provider calls require
`--confirm-real-llm`, and DeepSeek is disabled for non-smoke real runs unless
`ALLOW_DEEPSEEK_EVALUATION=1` is set.
