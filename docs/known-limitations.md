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
