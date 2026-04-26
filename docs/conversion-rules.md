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
