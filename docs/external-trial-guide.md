# External Trial Guide

This guide is for a small external JAVA2GO trial.

The goal of the trial is not to prove full Java compatibility. The goal is to
help an external developer run a small evaluation, understand the report, and
decide whether JAVA2GO reduces migration effort for their use case.

## What JAVA2GO Is

JAVA2GO is a project-level Java-to-Go migration workflow with:

- Java project analysis
- LLM-assisted Go code generation
- generated Go test generation
- conservative conversion status reporting
- project-level next-step guidance

## What JAVA2GO Is Not

JAVA2GO is not:

- a full Java compatibility layer
- a general LLM gateway
- a framework-complete Spring/JPA migration tool
- proof of Java-to-Go semantic equivalence

## Recommended Trial Inputs

Start with one of these small inputs:

### Trial Input 1: Mostly Supported Path

```text
benchmark_dataset/tier5_polymorphism/01_payment_processor
```

Why use it:

- small and understandable
- demonstrates a clean success path when the current supported scope fits
- already used for the accepted tier5 smoke evidence

Expected shape:

- `conversionStatus: success`
- build/test success

### Trial Input 2: Honest Partial Path

```text
benchmark_dataset/tier8_io_json/01_config_parser
```

Why use it:

- small but realistic backend startup/config logic
- demonstrates parser/config review needs
- shows how `partial` can still be useful and actionable

Expected shape:

- `conversionStatus: partial`
- parser/config caveat reasons
- next actions for review

## Safe Low-Cost Default Path

Default trial commands do not require API keys and do not call real LLMs.

Run automated checks:

```powershell
python -m unittest discover -s tests
python -m py_compile scripts/run_layered_evaluation_suite.py llm_profiles.py workflow.py multi_agent_workflow.py server.py logging_config.py security.py conversion_status.py
git diff --check
```

Run mock layered suites:

```powershell
python scripts/run_layered_evaluation_suite.py --suite smoke --output run_logs/layered_eval_smoke_mock_latest.json
python scripts/run_layered_evaluation_suite.py --suite core --output run_logs/layered_eval_core_mock_latest.json
```

These commands let a trial user see:

- suite structure
- report fields
- status model
- low-cost verification path

without spending money on real LLM calls.

## Optional Real LLM Confirmation Path

Only run this manually if the trial user wants one paid confirmation.

Recommended command:

```powershell
python scripts/run_layered_evaluation_suite.py --suite core --profile codex-proxy --confirm-real-llm --output run_logs/layered_eval_core_codex_proxy_external_trial_confirmation.json
```

Important:

- This may cost money.
- This requires local API key setup.
- DeepSeek is not part of the default trial path.

Do not run DeepSeek or wave1 by default for external trials.

## Reading The Report

Use `docs/reporting-guide.md` alongside the JSON report.

Read these fields first:

- `llmCallStatus`
- `conversionStatus`
- `statusReasons`
- `recommendedNextActions`

For project-level runs, also read:

- `projectStatusSummary`
- `conversionItems`
- `summaryCompleteness`

Remember:

```text
build/test success does not prove full Java semantic equivalence.
```

## Known Limitations To Expect In Trial

Before treating a `partial` or `unsupported` result as a bug, review:

- `docs/known-limitations.md`

Especially important:

- checked exceptions remain unsupported/partial
- Java generics remain unsupported
- framework annotations remain unsupported
- stream pipelines remain unsupported
- parser/config support is currently a narrow subset only

## Safe Trial Expectations

A good external trial means:

- setup is clear
- the default mock path is understandable and low cost
- one small real run is possible if the user chooses
- reports explain why a result is `success`, `warning`, `partial`, or `unsupported`
- next actions are clear enough to guide manual review

A good external trial does not require:

- full Java project success
- framework support
- full semantic equivalence proof
- multiple expensive model runs

## Next Documents

- Trial checklist: `docs/external-trial-checklist.md`
- Feedback template: `docs/external-trial-feedback-template.md`
- Reporting guide: `docs/reporting-guide.md`
