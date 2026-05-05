# Reporting Guide

This guide explains how to read JAVA2GO MVP reports.

JAVA2GO reports separate:

- LLM/API execution status
- conversion support status
- engineering validation status

These are related, but they are not the same thing.

## Status Fields

### `llmCallStatus`

This answers:

```text
Did the selected LLM profile call succeed?
```

Typical values:

- `success`: the LLM/API call succeeded.
- `error`: the LLM/API call failed.

Important:

```text
llmCallStatus=success does not mean the Java-to-Go conversion is fully supported.
```

### `conversionStatus`

This answers:

```text
How trustworthy is the Java-to-Go conversion outcome within JAVA2GO's current supported scope?
```

Values:

- `success`: converted safely within supported scope.
- `warning`: converted with caveats that should be reviewed.
- `partial`: only part of the behavior is supported; manual follow-up is needed.
- `unsupported`: known unsupported Java feature.
- `error`: unexpected conversion failure.

Important:

```text
Build/test success cannot upgrade a known limitation to success.
```

### Engineering status

Reports may include:

```json
"engineeringStatus": {
  "build": "success",
  "tests": "partial",
  "testGeneration": "partial",
  "testQuality": "success"
}
```

These fields answer:

- Did generated Go build?
- Did generated Go tests pass?
- Did generated tests exist and look usable?

Important:

```text
Engineering success is necessary for trust, but it is not proof of full semantic conversion success.
```

## Why A Report Can Be `partial` Even When Go Builds

This is expected for the current MVP.

Examples:

- Java exception flow was converted, but Go error-return design still needs review.
- Parser/config behavior builds, but missing-key/default/error-path semantics need review.
- Unsupported features are still present in the input, even if some output files build.

## `statusReasons`

`statusReasons` explain why the report was downgraded below `success`.

Example:

```json
"statusReasons": [
  "Detected parser/config behavior; defaults and error paths may require review."
]
```

Prefer reading `statusReasons` before reading raw logs.

When available, `statusReasonDetails` provides structured categories.

Example categories:

- `config_map_lookup_missing_key_caveat`
- `config_default_value_fallback`
- `config_required_field_error_return`
- `config_parse_failure_error_return`
- `config_dynamic_or_framework_unsupported`

## `recommendedNextActions`

These are short follow-up steps derived from statuses and reasons.

Example:

```json
"recommendedNextActions": [
  "Review parser/config modules for default-value, JSON mapping, and error-path semantics.",
  "Inspect modules with generated test failures before trusting project-level behavior."
]
```

These actions are guidance, not proof that full migration is complete.

## Project-Level Reports

Project-level reports may include:

- `projectStatusSummary`
- `summaryCompleteness`
- `conversionItems`
- `testFailureExplanations`
- `testGenerationReasons`
- `testIssueCategories`

### `projectStatusSummary`

This is a count of module/file-level items by status.

Example:

```json
"projectStatusSummary": {
  "success": 6,
  "warning": 3,
  "partial": 2,
  "unsupported": 0,
  "error": 0
}
```

### `summaryCompleteness`

This explains whether the counts fully explain the aggregate project status.

- `complete`: item-level status coverage is sufficient to explain the aggregate status.
- `incomplete`: item-level items exist, but they do not fully explain the aggregate status yet.
- `aggregate-only`: only aggregate status is reliable; detailed counts are incomplete.

### `conversionItems`

These identify which module/file contributes to `warning`, `partial`, or `unsupported`.

Example:

```json
{
  "id": "mod2",
  "status": "warning",
  "semanticStatus": "success",
  "classifierStatus": "warning",
  "reasons": [
    "Detected parser/config behavior; defaults and error paths may require review."
  ],
  "engineeringStatus": {
    "build": "success",
    "tests": "success",
    "testGeneration": "success",
    "testQuality": "success"
  }
}
```

## Reading Missing Token Usage

If a provider omits token usage, reports must keep it as null/unknown.

Example:

```json
"tokenUsage": {
  "promptTokens": null,
  "completionTokens": null,
  "totalTokens": null
}
```

This means:

```text
The provider did not expose usage data here.
```

It does not mean the call cost zero tokens.

## Example Report Fragment

```json
{
  "llmCallStatus": "success",
  "conversionStatus": "partial",
  "statusReasons": [
    "Detected parser/config behavior; defaults and error paths may require review."
  ],
  "engineeringStatus": {
    "build": "success",
    "tests": "success",
    "testGeneration": "success",
    "testQuality": "success"
  },
  "recommendedNextActions": [
    "Review parser/config modules for default-value, JSON mapping, and error-path semantics."
  ]
}
```

Interpretation:

```text
The model/API call succeeded, generated Go passed engineering checks, but the conversion still needs parser/config review and should not be treated as fully safe success.
```
