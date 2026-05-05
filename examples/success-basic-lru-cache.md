# Success Example: Basic LRU Cache

Fixture:

```text
benchmark_dataset/tier1_basic/01_lru_cache
```

Expected status:

```text
success
```

Why this is a success example:

- The fixture is part of the supported narrow core set.
- It represents a basic class/method + map-backed behavior pattern.
- In accepted core evaluation, this fixture reached `conversionStatus: success`.

Example report fragment:

```json
{
  "fixture_id": "core.basic_lru_cache",
  "llmCallStatus": "success",
  "conversionStatus": "success",
  "statusReasons": [],
  "engineeringStatus": {
    "build": "success",
    "tests": "success",
    "testGeneration": "success",
    "testQuality": "success"
  }
}
```

Interpretation:

```text
This fixture converted within the currently supported scope and passed engineering validation without known caveat signals.
```

Important limit:

```text
This is a fixture-specific success example. It does not prove full Java compatibility.
```
