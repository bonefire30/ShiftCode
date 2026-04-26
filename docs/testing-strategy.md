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

## Failure Case Database

Track important failed or partial conversions using this format.

| Case | Status | Root Cause | Expected Behavior | Regression Test |
| --- | --- | --- | --- | --- |
| TBD | TBD | TBD | TBD | TBD |
