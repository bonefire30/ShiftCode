# Partial Example: Parser/Config Subset

Fixtures:

```text
benchmark_dataset/tier8_io_json/01_config_parser
benchmark_dataset/tier8_parser_config/03_required_field
benchmark_dataset/tier8_parser_config/04_parse_failure
```

Expected status:

```text
partial
```

Why this is not full success:

- Required-field validation in Java throws must become explicit Go error returns.
- Parse failures must become explicit Go error returns.
- Startup/config semantics can still differ even when the generated Go builds.

Example report fragment:

```json
{
  "llmCallStatus": "success",
  "conversionStatus": "partial",
  "statusReasonDetails": [
    {
      "category": "config_required_field_error_return",
      "status": "partial",
      "message": "Detected required config field validation; Java exception flow should become explicit Go error returns and needs review."
    },
    {
      "category": "config_parse_failure_error_return",
      "status": "partial",
      "message": "Detected config parse failure path; Java parse errors should become explicit Go error returns and need review."
    }
  ],
  "recommendedNextActions": [
    "Review parser/config modules for default-value, JSON mapping, and error-path semantics.",
    "Review startup error handling; Java exception flow was converted to Go error returns."
  ]
}
```

Interpretation:

```text
The generated Go may build and look reasonable, but parser/config behavior still needs human review before the migration can be treated as safely complete.
```

Important limit:

```text
JAVA2GO supports only a narrow parser/config subset. This example does not imply full parser/config or framework configuration support.
```
