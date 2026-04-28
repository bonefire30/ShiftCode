# ShiftCode

ShiftCode is a project-level Java-to-Go migration system built around a
multi-agent workflow. The product now supports only the project migration
path: analyze a Java project, translate modules, generate Go tests, and repair
the output until `go build` / `go test` pass.

## 当前开发进度

ShiftCode 当前处于 JAVA2GO 项目级迁移工作流的早期 Beta 阶段。核心目标不是
宣称完整 Java 兼容，而是把每次转换做得可验证、可解释、可回归。

已经完成的能力：

- 项目级 Java 输入分析：AST 解析、依赖图构建、模块拆分和符号表上下文。
- LLM 驱动的 Go 代码生成和 `*_test.go` 测试生成。
- `go build ./...` / `go test ./...` 审查和有限自动修复循环。
- 固定三档 LLM 评估 profile：`minimax`、`deepseek`、`codex-proxy`。
- LLM 运行元数据记录：profile、provider、model、base URL、延迟、token usage、
  `llmCallStatus` 和 `conversionStatus`。
- mock/dry-run 路径，常规自动化测试不会调用真实 LLM API。
- tier5 payment polymorphism 三 profile smoke 验收报告。

当前质量证据：

- 单元测试：`python -m unittest discover -s tests`，40 个测试通过。
- Python 编译检查覆盖核心后端文件和 smoke 脚本。
- 最终 smoke 样例：`run_logs/tier5_three_profile_smoke_20260426_163606.json`。
- 已知限制和 smoke 验收口径记录在 `docs/known-limitations.md`、
  `docs/testing-strategy.md` 和 `docs/llm-evaluation-acceptance.md`。

当前限制：

- smoke pass 不等于完整 Java 语义等价。
- 当前只验证了有限 fixture，真实项目迁移仍需要人工 review。
- LLM profile 是评估候选，不是通用模型网关，也不代表 provider-wide support。
- unsupported、partial 和 failed conversion 必须继续明确标记，不能被 LLM 调用成功掩盖。

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

## Layered Evaluation Suites

Use layered suites before any full wave1 evaluation:

```powershell
python scripts/run_layered_evaluation_suite.py --suite smoke
python scripts/run_layered_evaluation_suite.py --suite core
python scripts/run_layered_evaluation_suite.py --suite features
```

These default to mock mode and do not call real LLM APIs. Real calls require an
explicit profile and confirmation:

```powershell
python scripts/run_layered_evaluation_suite.py --suite smoke --profile codex-proxy --confirm-real-llm
```

`wave1` is retained as a stage-gate benchmark for release/model decisions, not a
daily debugging suite. DeepSeek is disabled for non-smoke real runs unless
`ALLOW_DEEPSEEK_EVALUATION=1` is set.
