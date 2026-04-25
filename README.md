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

- `OPENAI_API_KEY` and related model settings are read from `.env`.
- Go must be installed and available on `PATH`.
- Optional MCP and skill integrations are still supported by the project-level
  agents.
