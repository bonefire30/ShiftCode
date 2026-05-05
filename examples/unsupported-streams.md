# Unsupported Example: Java Stream Pipeline

Fixture:

```text
benchmark_dataset/tier6_streams/01_data_analyzer
```

Expected status:

```text
unsupported
```

Why this is unsupported:

- Java stream pipelines require semantic rewriting, not just syntax translation.
- Current JAVA2GO rules do not claim broad stream support.

Example report fragment:

```json
{
  "fixture_id": "core.stream_data_analyzer",
  "llmCallStatus": "success",
  "conversionStatus": "unsupported",
  "statusReasons": [
    "Detected Java stream pipeline; stream pipelines are currently unsupported."
  ],
  "recommendedNextActions": [
    "Rewrite stream-based logic manually or add explicit conversion-rule support before trusting generated behavior."
  ]
}
```

Interpretation:

```text
The model call can succeed and generated Go can still be reported as unsupported because the Java feature is outside JAVA2GO's currently supported scope.
```

Important limit:

```text
`llmCallStatus: success` does not mean stream conversion is supported.
```
