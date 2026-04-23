# ShiftCode — Java → Go 智能迁移平台

基于 **LangGraph 多智能体工作流**的 Java 到 Go 代码迁移系统，支持单文件评测与多文件项目级迁移，提供实时可视化前端看板。

**源码仓库：** [github.com/bonefire30/ShiftCode](https://github.com/bonefire30/ShiftCode)

---

## 目录

- [功能特性](#功能特性)
- [整体架构](#整体架构)
- [环境要求](#环境要求)
- [安装](#安装)
- [配置](#配置)
- [快速启动](#快速启动)
- [项目结构](#项目结构)
- [工作流详解](#工作流详解)
  - [单文件迁移模式](#单文件迁移模式)
  - [多文件项目迁移模式](#多文件项目迁移模式)
- [基准测试集](#基准测试集)
- [API 参考](#api-参考)
- [高级功能](#高级功能)
- [开发指南](#开发指南)

---

## 功能特性

- **双模式迁移**：单 Java 文件评测 + 完整项目级多文件迁移
- **多智能体并行**：按主题对 Java 文件聚类成模块，多个 Translate Agent 跨模块并行执行，相同主题在同一上下文内串行处理
- **Test-Gen Agent**：自动基于 Java 语义推断 Go API 契约，生成 `*_test.go` 测试文件，无需手写
- **自修正循环（ReAct）**：Agent 调用 `go build` / `go test`，根据编译/测试错误自动修正代码，最多循环至上限
- **全局修复节点**：翻译完成后统一编译，失败则回到全局 `global_repair` 节点并行修复所有模块
- **HITL（Human-in-the-Loop）**：检测到 Spring/框架依赖时暂停，等待人工决策后继续
- **长期学习**：成功迁移后写入 `learnings.json`，Agent 可通过 `search_learnings` 工具复用历史经验
- **RAG 代码库索引**：使用 ChromaDB 对已翻译 Go 代码进行向量检索，提供跨文件上下文
- **可视化前端**：Vite + React 实时看板，SSE 推送每个节点状态、Go 源码、终端输出
- **MCP 支持**：可接入外部 stdio MCP 服务器，扩展 Agent 工具集

---

## 整体架构

```
Java 源文件
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                   多智能体工作流（LangGraph）                      │
│                                                                 │
│  architect ──► hitl_gateway ──► translate_modules               │
│                                     │ (模块级并行)               │
│                                     ▼                           │
│                               merge_all                         │
│                                     │                           │
│                                     ▼                           │
│                            test_gen_modules                     │
│                              (Test-Gen Agent)                   │
│                                     │                           │
│                                     ▼                           │
│                               reviewer                          │
│                              /           \                      │
│                    global_repair    test_gen_repair              │
│                         └────────────────┘                      │
│                                     │ 成功                       │
│                                    END                          │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
Go 输出目录（project_migrations/out_xxxxx/）
```

---

## 环境要求

| 依赖 | 最低版本 | 说明 |
|------|---------|------|
| Python | 3.10+ | 推荐 3.12（Conda 环境） |
| Go | 1.21+ | `go` 必须在 `PATH` 上，用于编译/测试验证 |
| Node.js | 18+ | 前端开发服务器（可选，仅前端需要） |
| LLM API Key | — | OpenAI 兼容接口（支持 MiniMax / GPT 等） |

---

## 安装

若尚未下载代码，请先克隆：

```bash
git clone https://github.com/bonefire30/ShiftCode.git
cd ShiftCode
```

### 方式一：Conda（推荐）

```bash
# 创建 conda 环境（首次）
conda create -n shiftcode python=3.12 -y
conda activate shiftcode
pip install -r requirements.txt

# 或从 environment.yml 一键创建
conda env create -f environment.yml
conda activate shiftcode
```

### 方式二：pip

```bash
cd ShiftCode
pip install -r requirements.txt
```

### 前端依赖

```bash
cd frontend
npm install
```

---

## 配置

复制 `.env.example` 并重命名为 `.env`，填写 API 配置：

```env
# MiniMax 接口示例（兼容 OpenAI 格式）
OPENAI_API_KEY=在此处填写你的_API_Key
OPENAI_BASE_URL=https://api.minimax.chat/v1
OPENAI_MODEL=MiniMax-M2.7

# 使用 OpenAI 官方接口示例
# OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_MODEL=gpt-4o-mini
```

> **Windows 下 Go 未在 PATH 的临时解决**：
> ```powershell
> $env:PATH = "C:\Program Files\Go\bin;" + $env:PATH
> ```

---

## 快速启动

### 启动后端 API

```bash
conda activate shiftcode
uvicorn server:app --reload --host 127.0.0.1 --port 8000
```

### 启动前端开发服务器

```bash
cd frontend
npm run dev
```

浏览器访问 **http://127.0.0.1:5173**，即可看到迁移看板。

> Vite 已将 `/api` 代理到 `http://127.0.0.1:8000`，无需配置 CORS。

### 命令行直接运行工作流

```bash
# 真实 LLM 迁移（需配置 .env）
python workflow.py

# Stub 模式（不调用 API，验证流水线）
python workflow.py --stub
# 或
set MIGRATION_USE_STUB=1
python workflow.py
```

---

## 项目结构

```text
ShiftCode/
├── server.py                  # FastAPI 后端 + SSE 推送接口
├── workflow.py                # 单文件迁移 LangGraph 工作流 + run_module_agent / run_test_gen_module_agent
├── multi_agent_workflow.py    # 多文件项目迁移工作流（LangGraph，模块级并行）
├── agent_tools.py             # 所有 Agent 工具集（Translate / Test-Gen / Project）
├── dependency_graph.py        # Java 文件依赖图 + 模块聚类 + 拓扑分层
├── java_ast.py                # Java AST 解析（tree-sitter）+ 框架检测
├── symbol_table.py            # Go 符号表（跨文件类型共享）
├── codebase_rag.py            # ChromaDB 向量检索（已翻译 Go 代码的 RAG）
├── project_tools.py           # go build / go test / scan_java_project 等工具
├── evaluate.py                # 单文件评测 harness（go build + go test + golangci-lint）
├── learnings.py               # 长期记忆读写（learnings.json）
├── skills_loader.py           # Skill SOP 加载器
├── mcp_bridge.py              # MCP stdio 客户端桥接
├── logging_config.py          # 结构化日志（每次运行独立 log 文件）
│
├── benchmark_dataset/         # 基准测试集（8 个难度层）
│   ├── tier1_basic/01_lru_cache/
│   ├── tier2_oop/01_user_service/
│   ├── tier3_concurrency/01_downloader/
│   ├── tier4_generics/01_result_wrapper/
│   ├── tier5_polymorphism/01_payment_processor/
│   ├── tier6_streams/01_data_analyzer/
│   ├── tier7_exceptions/01_retry_executor/
│   └── tier8_io_json/01_config_parser/
│       # 每个用例含：source.java、golden_output.go、migration_prompt.txt（可选）
│
├── frontend/                  # Vite + React 前端
│   ├── src/App.tsx            # 单文件迁移看板
│   └── src/ProjectMigration.tsx  # 多文件项目迁移看板
│
├── project_migrations/        # Agent 生成的 Go 项目输出目录（自动创建）
│   └── out_xxxx/              # 每次迁移一个独立目录
│
├── run_logs/                  # 每次运行的结构化日志
├── skills/migration/SKILL.md  # Agent 迁移 SOP 技能文档
├── learnings.json             # 长期学习记忆（自动维护）
├── .env.example               # 环境变量示例
├── requirements.txt           # Python 依赖
└── environment.yml            # Conda 环境定义
```

---

## 工作流详解

### 单文件迁移模式

针对 `benchmark_dataset` 中的单个用例，通过前端"单文件迁移"标签或 `python workflow.py` 触发：

```
translator_node ──► qa_node ──► (repair_node) ──► reflect_node ──► END
```

| 节点 | 职责 |
|------|------|
| `translator_node` | ReAct Agent，工具：`read_file` / `write_file` / `edit_file` / `run_go_tests`，迭代直到测试通过 |
| `qa_node` | `go build` + `go test` 验证，成功则前进 |
| `repair_node` | 失败时注入错误提示，重新调用 translator，最多 N 次 |
| `reflect_node` | 成功后提炼学习经验，写入 `learnings.json` |

### 多文件项目迁移模式

针对任意含多个 Java 文件的目录，通过前端"项目迁移"标签或 API 触发：

#### 1. `architect` — 项目分析

- 扫描所有 Java 文件，提取类名、包名、依赖关系
- 使用 tree-sitter 解析 Java AST
- 构建文件级依赖图，聚类成**主题模块**（相关文件放同一模块）
- 生成模块间拓扑排序（依赖层次），决定翻译顺序
- 初始化 Go 输出目录和 `go.mod`

#### 2. `hitl_gateway` — 人机决策门

- 检测到 Spring / JPA / Hibernate 等框架标志时，**暂停工作流**
- 前端弹出决策表单（接受 / 拒绝 / 自定义指令）
- 用户提交后通过 `POST /api/project/hitl/decide` 恢复流程

#### 3. `translate_modules` — 模块级并行翻译

- 按拓扑层次顺序处理各模块
- 同一层内所有模块通过 **`ThreadPoolExecutor` 并行执行**
- 每个模块启动一个独立的 `Translate Agent`（ReAct 循环）：
  - 工具集：`read_file` / `write_file` / `edit_file` / `run_go_build` / `list_module_files`
  - 输出该模块所有 `.go` 源文件
  - 模块内文件按依赖顺序串行处理，共享上下文
- RAG 写入加锁（`threading.Lock`），读取免锁

#### 4. `merge_all` — 符号表合并

- 汇总所有模块产出的 Go 代码
- 注册全局符号表（类型、接口、函数签名）
- 供后续 Agent 做跨包类型对齐

#### 5. `test_gen_modules` — 测试生成（并行）

- 对每个模块启动独立的 **`Test-Gen Agent`**（`ThreadPoolExecutor` 并行）
- 系统提示词明确约束：**实现文件已由 Translate Agent 生成，Test-Gen Agent 只能写 `*_test.go`**
- Agent 仅通过编译错误反馈推断 Go API 契约（黑盒测试），不读取实现源码
- 工具集：`write_test_file` / `edit_test_file` / `run_go_tests_only`

#### 6. `reviewer` — 统一验证

- 对整个输出目录执行 `go build ./...` + `go test -count=1 ./...`
- 成功 → `END`
- 失败 → 根据修复轮次路由到修复节点

#### 7. `global_repair` / `test_gen_repair` — 修复循环

| 修复节点 | 触发条件 | 行为 |
|---------|---------|------|
| `global_repair` | 编译失败或早期测试失败 | 并行重跑所有 Translate Agent，传入聚合错误日志作为 hint |
| `test_gen_repair` | 编译通过但测试失败（后期轮次） | 并行重跑所有 Test-Gen Agent，传入测试失败日志作为 hint |

---

## 基准测试集

8 个难度梯度，覆盖从基础语法到复杂 IO 的 Java 特性：

| Tier | 目录 | Java 特性 | Go 映射 |
|------|------|-----------|---------|
| 1 | `tier1_basic/01_lru_cache` | 基础语法、容器 | map + 双向链表 |
| 2 | `tier2_oop/01_user_service` | OOP、构造函数、错误 | struct + `(T, error)` |
| 3 | `tier3_concurrency/01_downloader` | ExecutorService、CountDownLatch | goroutine + WaitGroup |
| 4 | `tier4_generics/01_result_wrapper` | Java 泛型 | Go 泛型（1.18+） |
| 5 | `tier5_polymorphism/01_payment_processor` | 抽象类、多态 | interface + 具体 struct |
| 6 | `tier6_streams/01_data_analyzer` | Stream API、分组 | map + 循环 |
| 7 | `tier7_exceptions/01_retry_executor` | try/catch/finally | errors + defer |
| 8 | `tier8_io_json/01_config_parser` | InputStream + JSON | `io.Reader` + `encoding/json` |

每个用例包含：
- `source.java` — 待迁移的 Java 源码
- `golden_output.go` — 参考实现（用于 Stub 模式和评分参考）
- `migration_prompt.txt`（部分用例）— 覆盖默认翻译提示词

> **注意**：`expected_test.go` 已从基准集中移除，统一由项目迁移流程中的 `Test-Gen Agent` 按 Java 语义自动生成 `*_test.go`。若需使用 `python evaluate.py` 单独评测某目录，请自行在该目录提供 `expected_test.go`。

---

## API 参考

### 基础接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/cases` | 列举所有可用基准用例 |
| `GET` | `/api/case/source?case=<path>` | 读取指定用例的 `source.java` |

### 单文件迁移

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/migrate/stream` | SSE 流式推送单文件迁移进度 |

**查询参数**：
- `case` — 用例路径，如 `benchmark_dataset/tier2_oop/01_user_service`
- `use_stub` — 是否使用黄金实现（默认 `false`）
- `max_calls` — 最大 translator 调用次数（默认 3）
- `use_legacy` — 是否使用旧版一次性输出模式（默认 `false`）

### 项目迁移

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/project/analyze` | 分析项目，返回文件列表、模块信息 |
| `GET` | `/api/project/migrate/stream` | SSE 流式推送多文件项目迁移进度 |
| `POST` | `/api/project/hitl/decide` | HITL 人机决策，恢复暂停的工作流 |

**SSE 事件类型**：

```jsonc
// 节点状态更新
{ "type": "step", "node": "translate_modules", "state": { ... } }

// 流式 token（legacy 模式）
{ "type": "chunk", "content": "func " }

// 完成
{ "type": "done" }

// 错误
{ "type": "error", "message": "..." }
```

---

## 高级功能

### 长期记忆

成功迁移后，`reflect` 节点自动提炼经验写入 `learnings.json`。Agent 在迁移时可通过工具主动查询：

```python
# Agent 工具调用示例
search_learnings(query="Java ExecutorService to goroutine")
record_learning(topic="sync.WaitGroup", content="Add before goroutine start")
```

### RAG 代码库检索

`codebase_rag.py` 使用 ChromaDB 对已翻译的 Go 代码建立向量索引，Agent 可查询相关上下文，提升跨文件类型一致性。

### MCP 工具扩展

安装 `mcp` 包后，设置环境变量即可接入外部 MCP 服务器：

```env
MIGRATION_MCP_COMMAND=["npx", "-y", "@some/mcp-server"]
```

Agent 工具中的 `mcp_query` / `mcp_status` 会自动路由到该服务器。

### Skill SOP

`skills/migration/SKILL.md` 定义了迁移 SOP，Agent 可通过 `load_skill_tool` 读取，`list_available_skills` 列出所有可用 Skill。

使用 `SKILL_ROOT` 环境变量可指定自定义 Skill 根目录。

### 结构化日志

每次迁移在 `run_logs/` 下生成独立日志文件（JSON Lines 格式），记录：
- 每个节点的进入/退出时间和关键指标
- Agent 的 ReAct 完整调用链
- 工具调用结果（build 日志、test 输出）
- Token 用量统计

---

## 开发指南

### 评测

```bash
# 用黄金实现验证流水线（不调用 LLM）
python evaluate.py --use-golden -o report.md

# 指定手写的 output.go 做评测
python evaluate.py --code path/to/output.go
```

### 构建前端（生产）

```bash
cd frontend
npm run build
# 产物在 frontend/dist/
```

### 环境变量速查

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OPENAI_API_KEY` | — | LLM API Key（必填） |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | API Base URL |
| `OPENAI_MODEL` | `gpt-4o-mini` | 使用的模型名称 |
| `MIGRATION_USE_STUB` | `0` | `1` 时使用黄金实现，不调用 LLM |
| `MIGRATION_USE_AGENT` | `1` | `0` 时切换到旧版一次性输出模式 |
| `MIGRATION_KEEP_WORKSPACE` | `0` | `1` 时保留 Agent 临时工作区（调试用） |
| `MIGRATION_MCP_COMMAND` | — | MCP 服务器启动命令（JSON 数组字符串） |
| `SKILL_ROOT` | `skills/` | Skill SOP 根目录 |
