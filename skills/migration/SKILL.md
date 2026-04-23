# Java → Go migration (MVP / benchmark)

## Principles

- Match the public API in `expected_test.go` in the case directory, not a literal line-by-line port.
- One primary module file: `output.go` in the agent workspace; package name must follow `migration_prompt.txt` if present.
- After edits, use `run_go_tests` in the tool loop: green means compile and tests both pass.
- If tests fail, read the failure output, then `read_file` / `edit_file` on `output.go` (or `write_file` for full rewrites in small files).

## Concurrency (ExecutorService → goroutines)

- Use `sync.WaitGroup` to wait; protect shared `map` with a mutex.
- Do not use busy loops; do not `panic` in helpers.

## Pitfalls to avoid

- Go does not have exceptions; return `(T, error)` and document contract.
- `WaitGroup` must `Add` before the goroutine starts, or the count is wrong.
- `nil` vs empty slice: match test expectations (nil map vs empty map) when the prompt requires it.

## Optional next steps (Tier 4)

- Split `output.go` into multiple files only if the case adds subpackages; the benchmark harness still evaluates `output.go` only unless extended.
