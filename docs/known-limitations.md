# Known Limitations

This document should be updated whenever JAVA2GO discovers or introduces a known limitation.

## Current Policy

- Unsupported Java features must be reported explicitly.
- Partial support must not be presented as full support.
- Failed conversions should explain what failed and where possible what the user can do next.
- Generated Go should prefer idiomatic, maintainable output over mechanical Java-shaped code.

## Known Limitation Template

~~~md
## <Limitation Name>

Status: partial | unsupported | error

Affected Java pattern:

```java
// Example
```

Current behavior:
- <What JAVA2GO does now>

Expected future behavior:
- <What better support would look like>

User guidance:
- <What the user should do now>
~~~

## Limitations

| Area | Status | Notes | User Guidance |
| --- | --- | --- | --- |
| Checked exceptions | unsupported | Go uses explicit error returns instead of checked exceptions. | Review affected methods and design error returns manually. |
| Java generics | unsupported | Type parameter semantics need explicit Go mapping. | Review generated output before relying on it. |
| Framework annotations | unsupported | Annotation behavior depends on the Java framework. | Treat framework behavior as manual migration work. |
| Stream pipelines | unsupported | Streams require semantic rewriting. | Rewrite into loops or Go iterator-style code manually. |
| LLM profile evaluation | partial | The `minimax`, `deepseek`, and `codex-proxy` profiles are evaluation candidates, not a general model gateway or guarantee of provider-wide support. | Treat profile results as comparative evidence for selected fixtures only. |
| Provider model identifiers | partial | Provider and proxy endpoints may require model identifiers that differ from initial planning labels. The report `model` field records the actual endpoint-accepted identifier used in API requests. | Use the configured profile and smoke report model values when reproducing evaluations. |
| Smoke semantic signal | partial | The tier5 smoke test checks a fixture-specific payment contract and build/test status. It does not prove complete Java semantic equivalence. | Review generated Go for production migrations and add fixture-specific semantic checks as coverage expands. |
| Provider token usage | partial | Providers may omit token usage or expose only aggregate totals. Missing values are reported as null/unknown, not estimated. | Use token data only when present in the report. |
| Parser/config subset | partial | JAVA2GO currently supports only a narrow parser/config subset: map-backed lookup, default fallback, required-field validation, and simple parse failure. Framework, dynamic, and nested config behavior remain unsupported. | Review missing-key behavior, defaults, and startup error handling before trusting converted config logic. |
