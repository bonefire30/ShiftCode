# Conversion Rules

This document is the source of truth for Java-to-Go conversion behavior.

## Status Model

- success: converted safely with equivalent or intentionally idiomatic Go behavior.
- warning: converted with caveats that the user should review.
- partial: partially supported; output may require manual follow-up.
- unsupported: known Java feature that JAVA2GO does not convert yet.
- error: unexpected conversion failure.

## Rule Template

Use this template when adding or changing a conversion rule.

~~~md
## Rule: <Java Feature>

Status: success | warning | partial | unsupported | error

Java input pattern:

```java
// Example Java input
```

Go output pattern:

```go
// Expected Go output
```

Semantic assumptions:
- <Assumption>

Unsupported edge cases:
- <Edge case>

Warning or error behavior:
- <Message or behavior>

Tests:
- <Test file or planned test>
~~~

## Coverage Matrix

| Java Feature | Status | Notes | Tests |
| --- | --- | --- | --- |
| Classes | partial | Basic class-to-struct behavior should be tracked here. | TBD |
| Interfaces | partial | Interface method sets and implementation mapping need explicit rules. | TBD |
| Methods | partial | Receiver, visibility, overload handling, and return behavior need tests. | TBD |
| Fields | partial | Static, final, default values, and visibility need explicit handling. | TBD |
| Packages and imports | partial | Java package layout to Go module/package mapping needs project-level rules. | TBD |
| Exceptions | unsupported | Java checked exceptions do not map directly to Go errors. | TBD |
| Generics | unsupported | Java generics require explicit constraints and type parameter strategy. | TBD |
| Annotations | unsupported | Annotation semantics vary by framework and need policy decisions. | TBD |
| Collections | partial | Common Java collections need idiomatic Go equivalents and warnings. | TBD |
| Streams | unsupported | Stream pipelines need semantic rewriting, not syntax translation. | TBD |
| Concurrency | unsupported | Threading, executors, synchronized, volatile, and locks need careful mapping. | TBD |
| Parser/config map lookup | warning | Simple `config.get("key")` can convert structurally, but missing-key and zero-value behavior must be reviewed. | `benchmark_dataset/tier8_parser_config/01_map_lookup` |
| Parser/config default fallback | warning | `getOrDefault` can map to explicit Go fallback, but default/missing-key behavior must be verified. | `benchmark_dataset/tier8_parser_config/02_default_fallback` |
| Parser/config required validation | partial | Null/containsKey validation plus Java throw should become explicit Go error returns and still needs review. | `benchmark_dataset/tier8_parser_config/03_required_field` |
| Parser/config parse failure | partial | Simple parse failures can map to explicit Go error returns, but error-path behavior remains reviewable. | `benchmark_dataset/tier8_parser_config/04_parse_failure` |

## Rule: Parser/Config Map-Backed Lookup

Status: warning

Java input pattern:

```java
String host = config.get("host");
```

Go output pattern:

```go
host := config["host"]
```

Semantic assumptions:
- The Java source uses a plain map-backed lookup with no framework or reflection behavior.
- The generated Go keeps direct lookup semantics but may not distinguish missing key from empty value the same way callers expect.

Unsupported edge cases:
- Typed configuration frameworks.
- Nested binding, profile precedence, or dynamic runtime property sources.

Warning or error behavior:
- Report `config_map_lookup_missing_key_caveat` as `warning`.

Tests:
- `benchmark_dataset/tier8_parser_config/01_map_lookup`
- `tests/test_conversion_status.py`

## Rule: Parser/Config Default Value Fallback

Status: warning

Java input pattern:

```java
String port = config.getOrDefault("port", "8080");
```

Go output pattern:

```go
if value, ok := config["port"]; ok {
	return value
}
return "8080"
```

Semantic assumptions:
- The default applies only when the key is absent.
- The default value is a literal or otherwise directly portable.

Unsupported edge cases:
- Framework-managed defaults.
- Defaults that depend on other config sources or environment precedence.

Warning or error behavior:
- Report `config_default_value_fallback` as `warning` unless tests prove the missing-key behavior is fully preserved.

Tests:
- `benchmark_dataset/tier8_parser_config/02_default_fallback`
- `tests/test_conversion_status.py`

## Rule: Parser/Config Required Field Validation

Status: partial

Java input pattern:

```java
if (!config.containsKey("host") || config.get("host") == null) {
    throw new IllegalArgumentException("host is required");
}
```

Go output pattern:

```go
value, ok := config["host"]
if !ok || value == "" {
	return fmt.Errorf("host is required")
}
```

Semantic assumptions:
- Validation is local and explicit.
- Go may express the failure as an error return instead of Java throw semantics.

Unsupported edge cases:
- Framework-driven validation annotations.
- Validation that depends on object lifecycle or runtime injection.

Warning or error behavior:
- Report `config_required_field_error_return` as `partial`.

Tests:
- `benchmark_dataset/tier8_parser_config/03_required_field`
- `tests/test_conversion_status.py`

## Rule: Parser/Config Simple Parse Failure

Status: partial

Java input pattern:

```java
int timeout = Integer.parseInt(config.get("timeout"));
```

Go output pattern:

```go
timeout, err := strconv.Atoi(config["timeout"])
return timeout, err
```

Semantic assumptions:
- The parse operation is direct and local.
- Go preserves failure as an explicit error return.

Unsupported edge cases:
- Complex parser composition.
- Framework-specific binding and validation behavior.

Warning or error behavior:
- Report `config_parse_failure_error_return` as `partial`.

Tests:
- `benchmark_dataset/tier8_parser_config/04_parse_failure`
- `tests/test_conversion_status.py`
