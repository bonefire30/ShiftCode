# Development Standards

These standards define how JAVA2GO should be changed across product, engine, frontend, testing, and documentation work.

## Change Discipline

- Prefer the smallest correct change.
- Understand the existing code path before editing it.
- Avoid broad rewrites unless there is a concrete reason.
- Keep unrelated cleanup out of feature or bug-fix changes.
- Record important product or conversion decisions in docs instead of relying on chat history.

## Architecture Boundaries

- Parser code should focus on reading Java project structure and syntax.
- Transformer code should focus on semantic mapping from Java concepts to internal conversion decisions.
- Generator code should focus on producing idiomatic Go output.
- Reporter code should explain conversion status, warnings, partial support, unsupported features, and errors.
- UI code should display conversion state and results without embedding conversion engine rules.

## Review Expectations

- Any new conversion behavior should include tests or a clear reason tests cannot be added yet.
- Any known limitation introduced or discovered during implementation should be documented.
- Any user-visible status should use the shared status model: success, warning, partial, unsupported, or error.
