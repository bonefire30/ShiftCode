# Agent Context

JAVA2GO is a Java-to-Go conversion tool focused on correctness, explainability, and developer trust.

Use this file as a short index. Do not assume every project document is already in context. Read the relevant document before making decisions in that area.

## When To Read Project Docs

- For general engineering changes, read `docs/development-standards.md`.
- For test, benchmark, fixture, and example directory usage, read `docs/test-assets-structure.md`.
- For conversion engine behavior, read `docs/conversion-rules.md` before adding or changing Java-to-Go rules.
- For tests, regression coverage, or quality gates, read `docs/testing-strategy.md`.
- For roadmap, scope, or prioritization work, read `docs/product-roadmap.md`.
- For user-facing support claims, limitations, or unsupported Java features, read `docs/known-limitations.md`.
- For git, commit, push, branch, merge, tag, or PR work, read `docs/git-workflow.md`.

## Default Working Rules

- Keep changes small and reviewable.
- Preserve the status model from `AGENTS.md`: success, warning, partial, unsupported, error.
- Prefer documenting new conversion behavior in `docs/conversion-rules.md` instead of relying on chat history.
- Prefer documenting new limitations in `docs/known-limitations.md` when support is partial or unsupported.
- Do not run tests or commands that trigger LLM API calls; provide the command for the user to run instead.
- Do not create commits, push branches, merge, tag releases, rewrite history, or discard changes unless the user explicitly asks.
