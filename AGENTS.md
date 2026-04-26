# JAVA2GO Agent Instructions

These instructions apply to the entire repository.

JAVA2GO is a developer tool for converting Java projects into Go projects.
The core value of this project is conversion quality, explainability, and developer trust.

## Global Principles

- Always prefer small, reviewable changes.
- Do not rewrite unrelated code.
- Do not introduce large architectural changes without explaining why.
- Do not hide unsupported Java features.
- Do not claim full support unless tests prove it.
- Always distinguish supported, partially supported, unsupported, and failed conversions.
- Generated Go code should be idiomatic Go, not mechanical Java syntax translated into Go.

## Product Priorities

1. Correctness
2. Explainability
3. Test coverage
4. Developer experience
5. Performance
6. Visual polish

## Conversion Quality Rules

Every conversion rule should define:

- Java input pattern
- Go output pattern
- Semantic assumptions
- Unsupported edge cases
- Warning or error behavior
- Test cases

## Output Status Model

Use these statuses consistently:

- success: converted safely
- warning: converted with caveats
- partial: partially supported
- unsupported: known unsupported Java feature
- error: conversion failed unexpectedly

## Engineering Rules

- Prefer explicit data structures.
- Keep conversion rules testable.
- Keep parser, transformer, generator, and reporter responsibilities separate.
- Avoid mixing UI concerns with conversion engine logic.
- Add regression tests for every fixed bug.
- Add examples for every major supported Java feature.

## Testing And LLM API Calls

- When running code or tests would trigger LLM API calls or other long-running model/API operations, do not execute them directly.
- Instead, provide the exact command to the user and ask the user to run it locally and share the output.
- It is still acceptable to run tests or checks that do not call LLM APIs or perform long-running model/API operations.

## Safety Rules

- Never modify secrets or environment files.
- Never commit secrets, `.env` files, credentials, API keys, private logs, or generated temporary files.
- Never run destructive commands without explicit approval.
- Never auto-commit or auto-push.
- Never rewrite git history, amend commits, or force-push unless explicitly requested and confirmed.
- Never delete user files unless explicitly asked.
