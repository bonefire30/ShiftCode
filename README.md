# ShiftCode

ShiftCode is a project-level Java-to-Go migration system built around a
multi-agent workflow. The product now supports only the project migration
path: analyze a Java project, translate modules, generate Go tests, and repair
the output until `go build` / `go test` pass.

## What It Does

- Analyzes Java projects with AST parsing and dependency graph construction.
- Clusters files into translation modules and executes them in dependency order.
- Uses LLM-backed agents to translate Go code and generate `*_test.go` files.
- Reviews the generated project with `go build ./...` and `go test ./...`.
- Stores intermediate output under `project_migrations/` and logs under
  `run_logs/`.

## Architecture

- `server.py`: FastAPI server and SSE endpoints for project migration.
- `multi_agent_workflow.py`: project migration graph.
- `workflow.py`: shared module-translation and test-generation agent runners.
- `agent_tools.py`: project-level file, build, and test tool bindings.
- `dependency_graph.py`, `java_ast.py`, `symbol_table.py`: analysis helpers.
- `frontend/`: Vite + React dashboard for project migration only.

## API

- `GET /api/health`: health check.
- `GET /api/cases`: list benchmark directories that can be used as project inputs.
- `GET /api/llm-profiles`: list the fixed LLM profiles available for evaluation.
- `POST /api/project/analyze`: analyze a Java project directory.
- `GET /api/project/migrate/stream`: SSE stream for project migration progress.
- `POST /api/project/hitl/decide`: resume a paused migration after a HITL decision.

The old single-case endpoints were removed:

- `GET /api/migrate/stream`
- `GET /api/case/source`

## Local Development

### Backend

```powershell
python -m uvicorn server:app --reload --host 127.0.0.1 --port 8000
```

You can also use:

```powershell
.\scripts\run_backend.ps1
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend expects the backend at `http://127.0.0.1:8000`.

## Inputs

`benchmark_dataset/` is still kept as sample Java project input. Each case
directory contains:

- `source.java`
- `migration_prompt.txt`
- `golden_output.go`

The benchmark data remains useful as project input samples even though the
legacy single-case migration path has been removed.

## Notes

- LLM-backed migration supports exactly three evaluation profiles for now:
  `minimax`, `deepseek`, and `codex-proxy`.
- The `model` field records the actual endpoint-accepted model identifier used
  in API requests. The currently verified identifiers are `MiniMax-M2.7`,
  `deepseek-v4-flash`, and `GPT-5.3 Codex`.
- Profile API keys are read from environment variables only:
  `MINIMAX_API_KEY`, `DEEPSEEK_API_KEY`, and `CODEX_PROXY_API_KEY`.
- The `codex-proxy` profile uses `https://zhaoshuyue.net.cn/v1` with model
  `GPT-5.3 Codex`.
- `minimax` and `deepseek` require `MINIMAX_BASE_URL` or `DEEPSEEK_BASE_URL`
  when your environment exposes those providers through an OpenAI-compatible
  endpoint; JAVA2GO does not hardcode uncertain official endpoints.
- Select a profile through `GET /api/project/migrate/stream?...&llm_profile=deepseek`.
- For routine tests or dry runs, set `JAVA2GO_LLM_MOCK=1` to avoid real LLM API calls.
- Go must be installed and available on `PATH`.
- Optional MCP and skill integrations are still supported by the project-level
  agents.

## Manual LLM Verification

Do not run these as part of routine tests. After setting local API keys, verify
one profile at a time:

```powershell
$env:DEEPSEEK_API_KEY="..."
Invoke-WebRequest "http://127.0.0.1:8000/api/project/migrate/stream?project=benchmark_dataset/tier1_basic/01_lru_cache&llm_profile=deepseek"

$env:MINIMAX_API_KEY="..."
Invoke-WebRequest "http://127.0.0.1:8000/api/project/migrate/stream?project=benchmark_dataset/tier1_basic/01_lru_cache&llm_profile=minimax"

$env:CODEX_PROXY_API_KEY="..."
Invoke-WebRequest "http://127.0.0.1:8000/api/project/migrate/stream?project=benchmark_dataset/tier1_basic/01_lru_cache&llm_profile=codex-proxy"
```

SSE payloads include `llm_run_metadata` with profile, provider, model, latency,
token usage when available, and `llmCallStatus`. Per-file conversion state keeps
`conversionStatus` separate from LLM API call status.

For the fixed tier5 payment polymorphism smoke test across all three profiles,
run this manually after local API keys are configured:

```powershell
python scripts/run_tier5_three_profile_smoke.py
```

To run only one profile:

```powershell
python scripts/run_tier5_three_profile_smoke.py --profile deepseek
python scripts/run_tier5_three_profile_smoke.py --profile minimax
python scripts/run_tier5_three_profile_smoke.py --profile codex-proxy
```

The smoke report compares build/test status, generated-test quality, and a
fixture-specific source-structure semantic contract for
`tier5_polymorphism/01_payment_processor`. It does not append extra semantic
test files to the generated output directories. A passing smoke report does not
prove complete Java semantic equivalence or broad provider support; it is
evidence for this fixture and these configured profiles only.
