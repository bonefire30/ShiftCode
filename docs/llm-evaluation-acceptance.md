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

## Accepted Post-Wave1 Explainability Stage

The accepted follow-up wave1 report is:

```text
run_logs/layered_eval_wave1_codex_proxy_after_project_summary_v2.json
```

Accepted outcome:

- `llmCallStatus: success`
- `conversionStatus: partial`
- `expectedStatus: partial`
- `gateFailures: []`
- `projectStatusSummary` is present and consistent with project-level status.
- `summaryCompleteness: complete`.
- `conversionItems` identify module-level contributors to `warning` and `partial`.
- `testFailureExplanations` and `testGenerationReasons` are present.
- `recommendedNextActions` are actionable and status-driven.

Why this matters:

- Reviewers can explain why wave1 is `partial` without reading raw logs line by line.
- Module-level items no longer all appear as `success` when the project is `partial`.
- Engineering validation remains separate from conversion support status.
- The project output now tells developers what to inspect next instead of only saying `partial`.

Product interpretation:

```text
JAVA2GO now turns project-level partial results into clearer migration actions
by explaining which modules need review, why they need review, and what the
developer should do next.
```

## Accepted Feature-Coverage Roadmap P0

The accepted P0 scope from `feature-coverage-roadmap-from-wave1.md` focused on
test and test-generation partial explainability and recoverability.

Accepted evidence:

- Reports now include structured test/test-generation issue explanations.
- Reports distinguish converted-code support status from generated-test issues.
- Project-level partial results now include actionable next-step guidance.
- Wave1 partial results are more actionable without requiring additional model comparison runs.

Allowed release wording for this stage:

```text
JAVA2GO now turns project-level partial results into clearer migration actions by explaining test and generated-test issues separately from conversion support status.
```

## Accepted Parser/Config Conversion Subset

The accepted parser/config subset focuses on four narrow patterns only:

- map-backed config lookup
- default value fallback
- required-field validation
- simple parse failure

Accepted evidence:

- `docs/conversion-rules.md` documents all four parser/config subset rules.
- `conversion_status.py` emits specific parser/config categories:
  - `config_map_lookup_missing_key_caveat`
  - `config_default_value_fallback`
  - `config_required_field_error_return`
  - `config_parse_failure_error_return`
  - `config_dynamic_or_framework_unsupported`
- `evaluation_suites/manifest.json` defines the `parser-config` suite with four fixtures.
- `tests/test_conversion_status.py` covers the parser/config categories and status behavior.
- `run_logs/layered_eval_parser_config_mock_latest.json` shows conservative mock expectations:
  - map lookup -> `warning`
  - default fallback -> `warning`
  - required field validation -> `partial`
  - parse failure -> `partial`

Why this matters:

- Parser/config reports are now more specific than a generic caveat.
- Developers can distinguish missing-key/default review from required-field or parse-failure error-return review.
- The subset remains explicitly narrow and does not claim framework or broad config support.

Product interpretation:

```text
JAVA2GO now supports a narrow, test-backed parser/config subset with more useful
reasons and conservative statuses, while leaving framework and dynamic config
behavior explicitly out of scope.
```

## Accepted MVP Docs, Examples, And Reporting Stage

The accepted MVP packaging stage adds:

- `docs/reporting-guide.md`
- `examples/success-basic-lru-cache.md`
- `examples/partial-parser-config.md`
- `examples/unsupported-streams.md`

Accepted outcome:

- User-facing docs explain what JAVA2GO is and is not.
- Reporting guidance explains `llmCallStatus`, `conversionStatus`, engineering status, `statusReasons`, and `recommendedNextActions`.
- MVP examples cover `success`, `partial`, and `unsupported` outcomes.
- Real LLM checks remain manual and optional.
- Docs do not claim full Java compatibility or full parser/config support.

Why this matters:

- External users can now understand how to read MVP reports before trying a real project.
- Reviewers can assess the current supported scope without reading internal implementation code.
- Examples show the difference between safe success, partial parser/config behavior, and unsupported Java features.

Product interpretation:

```text
JAVA2GO now explains its MVP capabilities with concrete examples and report-reading guidance, so users can tell what is safe, what needs review, and what remains unsupported.
```

## Accepted External Trial Package

The accepted external trial package adds:

- `docs/external-trial-guide.md`
- `docs/external-trial-checklist.md`
- `docs/external-trial-feedback-template.md`

Accepted outcome:

- The default trial path is low-cost and does not require real LLM API keys.
- Trial inputs are small, understandable, and aligned with the current supported scope.
- The optional real LLM path is clearly manual and potentially paid.
- Trial docs explain what JAVA2GO is and is not, including the limits of `success`, `warning`, `partial`, and `unsupported`.
- The frontend trial path shows overall status, reasons, and next actions without implying full semantic equivalence.

Why this matters:

- An external developer can try the current MVP with minimal private project context.
- A reviewer can understand the report structure and current support scope without reading implementation code.
- Trial users can distinguish unsupported behavior from product bugs and continue manual migration with clearer expectations.

Product interpretation:

```text
JAVA2GO is now packaged well enough for a small external trial: users can start with a safe low-cost path, optionally run one paid confirmation, and read the resulting report honestly.
```
