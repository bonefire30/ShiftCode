import { useCallback, useEffect, useRef, useState } from 'react'
import { AnalysisSummary } from './components/migration/AnalysisSummary'
import { ErrorBanner } from './components/migration/ErrorBanner'
import { FileStatusPanel } from './components/migration/FileStatusPanel'
import { HitlDecisionPanel } from './components/migration/HitlDecisionPanel'
import { MigrationSetupPanel } from './components/migration/MigrationSetupPanel'
import { OutputPathNotice } from './components/migration/OutputPathNotice'
import { TerminalLogPanel } from './components/migration/TerminalLogPanel'
import { TestGenerationStatus } from './components/migration/TestGenerationStatus'
import { WorkflowTimeline } from './components/migration/WorkflowTimeline'
import type {
  CaseItem,
  FileState,
  HitlPayload,
  LlmEvaluationMetadata,
  LlmEvaluationProfile,
  StepRow,
} from './components/migration/types'

const API = ''

export function ProjectMigration() {
  const [cases, setCases] = useState<CaseItem[]>([])
  const [projectPath, setProjectPath] = useState('')
  const [analyze, setAnalyze] = useState<Record<string, unknown> | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [maxRepair, setMaxRepair] = useState(3)
  const [goModule, setGoModule] = useState('')
  const [llmProfile, setLlmProfile] = useState<LlmEvaluationProfile>('deepseek')
  const [running, setRunning] = useState(false)
  const [activeNode, setActiveNode] = useState<string | null>(null)
  const [steps, setSteps] = useState<StepRow[]>([])
  const [terminal, setTerminal] = useState('')
  const [fileStates, setFileStates] = useState<Record<string, FileState>>({})
  const [threadId, setThreadId] = useState<string | null>(null)
  const [lastState, setLastState] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [hitl, setHitl] = useState<HitlPayload | null>(null)
  const [runStartedAt, setRunStartedAt] = useState<number | null>(null)
  const [runEndedAt, setRunEndedAt] = useState<number | null>(null)
  const [currentTime, setCurrentTime] = useState<number | null>(null)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    fetch(`${API}/api/cases`)
      .then((r) => r.json())
      .then((data: CaseItem[]) => {
        setCases(data)
        if (data.length) {
          setProjectPath((prev) =>
            prev && data.some((c) => c.path === prev) ? prev : data[0].path
          )
        }
      })
      .catch(() =>
        setError(
          '无法连接后端。请先运行: uvicorn server:app --host 127.0.0.1 --port 8000'
        )
      )
  }, [])

  useEffect(() => {
    if (!running || !runStartedAt) return
    const id = window.setInterval(() => setCurrentTime(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [running, runStartedAt])

  const appendLog = useCallback((line: string) => {
    setTerminal((t) => t + (t ? '\n' : '') + line)
  }, [])

  const stop = useCallback(() => {
    esRef.current?.close()
    esRef.current = null
    setRunning(false)
  }, [])

  const runAnalyze = useCallback(() => {
    setAnalyzing(true)
    setError(null)
    setAnalyze(null)
    fetch(`${API}/api/project/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_dir: projectPath }),
    })
      .then((r) => {
        if (!r.ok) return r.text().then((t) => {
          throw new Error(t || String(r.status))
        })
        return r.json() as Promise<Record<string, unknown>>
      })
      .then((d) => {
        if ((d as { error?: string }).error) {
          setError((d as { error: string }).error)
        }
        setAnalyze(d)
      })
      .catch((e) => setError(String(e)))
      .finally(() => setAnalyzing(false))
  }, [projectPath])

  const startMigrate = useCallback(() => {
    if (running) return
    setError(null)
    setTerminal('')
    setSteps([])
    setFileStates({})
    setThreadId(null)
    setLastState(null)
    setHitl(null)
    const startedAt = Date.now()
    setRunStartedAt(startedAt)
    setCurrentTime(startedAt)
    setRunEndedAt(null)
    setRunning(true)
    appendLog('--- 项目迁移 (Agent Team) 开始 ---')
    const q = new URLSearchParams({
      project: projectPath,
      max_repair: String(maxRepair),
      llm_profile: llmProfile,
    })
    if (goModule.trim()) {
      q.set('go_module', goModule.trim())
    }
    const es = new EventSource(`${API}/api/project/migrate/stream?${q}`)
    esRef.current = es
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as {
          type: string
          message?: string
          node?: string
          state?: Record<string, unknown>
        }
        if (data.type === 'error') {
          setError(data.message || 'error')
          setRunEndedAt(Date.now())
          stop()
          return
        }
        if (data.type === 'done') {
          setActiveNode(null)
          appendLog('--- 流结束 ---')
          setRunEndedAt(Date.now())
          stop()
          return
        }
        if (data.type === 'step' && data.node) {
          const nodeName = data.node
          const now = Date.now()
          setActiveNode(nodeName)
          setSteps((prev) => [
            ...prev,
            { node: nodeName, at: new Date(now).toLocaleTimeString(), timestamp: now },
          ])
          const s = data.state || {}
          if (typeof s.thread_id === 'string') {
            setThreadId(s.thread_id)
          }
          setLastState(s)
          if (s.file_states && typeof s.file_states === 'object') {
            setFileStates(s.file_states as Record<string, FileState>)
          }
          const b = (s.last_build_log as string) || ''
          if (data.node === 'reviewer' && b) {
            appendLog(`[reviewer] build:\n${b.slice(0, 4000)}`)
          }
        }
        if (data.type === 'hitl') {
          setHitl(data as unknown as HitlPayload)
        }
      } catch {
        appendLog('(parse error) ' + ev.data)
      }
    }
    es.onerror = () => {
      appendLog('(EventSource 结束)')
      setRunEndedAt(Date.now())
      stop()
    }
  }, [appendLog, goModule, llmProfile, maxRepair, projectPath, running, stop])

  const sendHitl = useCallback(
    (decision: string) => {
      if (!threadId) return
      setHitl(null)
      appendLog(`--- HITL 决定: ${decision} ---`)
      fetch(`${API}/api/project/hitl/decide`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          thread_id: threadId,
          decision,
          key: hitl?.key,
        }),
      })
        .then((r) => r.json())
        .then((d) => {
          appendLog(JSON.stringify(d, null, 2).slice(0, 2000))
        })
        .catch((e) => setError(String(e)))
    },
    [appendLog, hitl?.key, threadId]
  )

  const testGenExpected =
    typeof lastState?.test_gen_expected_count === 'number'
      ? (lastState.test_gen_expected_count as number)
      : null
  const testGenGenerated =
    typeof lastState?.test_gen_generated_count === 'number'
      ? (lastState.test_gen_generated_count as number)
      : null
  const testGenOk =
    typeof lastState?.test_gen_ok === 'boolean'
      ? (lastState.test_gen_ok as boolean)
      : null
  const testGenFailures = Array.isArray(lastState?.test_gen_failures)
    ? (lastState.test_gen_failures as string[])
    : []
  const testGenWarnings = Array.isArray(lastState?.test_gen_warnings)
    ? (lastState.test_gen_warnings as string[])
    : []
  const testQualityOk =
    typeof lastState?.test_quality_ok === 'boolean'
      ? (lastState.test_quality_ok as boolean)
      : null
  const repairRound =
    typeof lastState?.repair_round === 'number'
      ? (lastState.repair_round as number)
      : null
  const lastBuildOk =
    typeof lastState?.last_build_ok === 'boolean'
      ? (lastState.last_build_ok as boolean)
      : null
  const lastTestOk =
    typeof lastState?.last_test_ok === 'boolean'
      ? (lastState.last_test_ok as boolean)
      : null
  const llmMetadata = extractLlmMetadata(lastState, llmProfile)

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-500">
        多文件：架构师建依赖图 → 批次自底向上翻译 → go build
        闭环修复。路径须位于仓库内。
      </p>

      <MigrationSetupPanel
        cases={cases}
        projectPath={projectPath}
        setProjectPath={setProjectPath}
        maxRepair={maxRepair}
        setMaxRepair={setMaxRepair}
        goModule={goModule}
        setGoModule={setGoModule}
        llmProfile={llmProfile}
        setLlmProfile={setLlmProfile}
        running={running}
        analyzing={analyzing}
        onAnalyze={runAnalyze}
        onStart={startMigrate}
        onStop={stop}
      />

      <TestGenerationStatus
        testGenExpected={testGenExpected}
        testGenGenerated={testGenGenerated}
        testGenOk={testGenOk}
        testGenFailures={testGenFailures}
        testGenWarnings={testGenWarnings}
        testQualityOk={testQualityOk}
      />

      <ErrorBanner error={error} />

      <HitlDecisionPanel hitl={hitl} onDecision={sendHitl} />

      <AnalysisSummary analyze={analyze} />

      {lastState && <LlmEvaluationSummary metadata={llmMetadata} />}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 min-h-[320px]">
        <WorkflowTimeline
          activeNode={activeNode}
          steps={steps}
          repairRound={repairRound}
          lastBuildOk={lastBuildOk}
          lastTestOk={lastTestOk}
          runStartedAt={runStartedAt}
          runEndedAt={runEndedAt}
          currentTime={currentTime}
        />
        <FileStatusPanel fileStates={fileStates} />
      </div>

      <OutputPathNotice goOutputDir={lastState?.go_output_dir} />

      <TerminalLogPanel terminal={terminal} />
    </div>
  )
}

function extractLlmMetadata(
  state: Record<string, unknown> | null,
  selectedProfile: LlmEvaluationProfile
): LlmEvaluationMetadata {
  const llm = asRecord(state?.llm_metadata) ?? asRecord(state?.llm) ?? asRecord(state?.model_metadata)
  const usage = asRecord(llm?.usage) ?? asRecord(llm?.token_usage) ?? asRecord(state?.token_usage)
  const error = asRecord(llm?.error) ?? asRecord(state?.llm_error)
  const profile = readString(llm?.profile) ?? readString(state?.llm_profile) ?? selectedProfile

  return {
    profile,
    provider: readString(llm?.provider) ?? readString(state?.llm_provider),
    model: readString(llm?.model) ?? readString(state?.llm_model),
    baseUrl: readString(llm?.baseUrl) ?? readString(llm?.base_url) ?? readString(state?.llm_base_url),
    latencyMs:
      readNumber(llm?.latencyMs) ?? readNumber(llm?.latency_ms) ?? readNumber(state?.llm_latency_ms),
    promptTokens:
      readNumber(usage?.promptTokens) ??
      readNumber(usage?.prompt_tokens) ??
      readNumber(usage?.input_tokens),
    completionTokens:
      readNumber(usage?.completionTokens) ??
      readNumber(usage?.completion_tokens) ??
      readNumber(usage?.output_tokens),
    totalTokens:
      readNumber(usage?.totalTokens) ??
      readNumber(usage?.total_tokens) ??
      readNumber(llm?.total_tokens) ??
      readNumber(state?.total_tokens),
    llmCallStatus:
      readString(llm?.llmCallStatus) ??
      readString(llm?.llm_call_status) ??
      readString(state?.llm_call_status) ??
      (error ? 'error' : 'unknown'),
    conversionStatus:
      readString(llm?.conversionStatus) ??
      readString(llm?.conversion_status) ??
      readString(state?.conversion_status),
    errorMessage:
      readString(error?.message) ?? readString(error?.detail) ?? readString(state?.llm_error_message),
    retryable: readBoolean(error?.retryable) ?? readBoolean(llm?.retryable),
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function readString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function readNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function readBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}

function formatLatency(latencyMs: number | null | undefined) {
  if (latencyMs === null || latencyMs === undefined) return 'unknown'
  if (latencyMs >= 1000) return `${(latencyMs / 1000).toFixed(1)}s`
  return `${Math.round(latencyMs)}ms`
}

function formatNumber(value: number | null | undefined) {
  return value === null || value === undefined ? 'unknown' : value.toLocaleString()
}

function llmStatusClass(status: string | null | undefined) {
  if (status === 'success') return 'border-emerald-800/70 bg-emerald-500/10 text-emerald-300'
  if (status === 'warning') return 'border-amber-800/70 bg-amber-500/10 text-amber-200'
  if (status === 'error') return 'border-red-800/70 bg-red-500/10 text-red-200'
  return 'border-slate-700 bg-slate-800/70 text-slate-400'
}

function conversionStatusClass(status: string | null | undefined) {
  if (status === 'success') return 'border-emerald-800/70 bg-emerald-500/10 text-emerald-300'
  if (status === 'warning') return 'border-amber-800/70 bg-amber-500/10 text-amber-200'
  if (status === 'partial') return 'border-sky-800/70 bg-sky-500/10 text-sky-200'
  if (status === 'unsupported') return 'border-orange-800/70 bg-orange-500/10 text-orange-200'
  if (status === 'error') return 'border-red-800/70 bg-red-500/10 text-red-200'
  return 'border-slate-700 bg-slate-800/70 text-slate-400'
}

function LlmEvaluationSummary({ metadata }: { metadata: LlmEvaluationMetadata }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-medium text-slate-200">LLM evaluation metadata</h3>
          <p className="mt-1 text-xs text-slate-500">
            API 调用状态只说明模型请求是否成功；转换状态仍必须单独判断。
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-[11px]">
          <span className={`rounded-full border px-2 py-1 ${llmStatusClass(metadata.llmCallStatus)}`}>
            LLM call {metadata.llmCallStatus || 'unknown'}
          </span>
          <span
            className={`rounded-full border px-2 py-1 ${conversionStatusClass(
              metadata.conversionStatus
            )}`}
          >
            Conversion {metadata.conversionStatus || 'unknown'}
          </span>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 text-xs md:grid-cols-5">
        <MetadataItem label="Profile" value={metadata.profile || 'unknown'} />
        <MetadataItem label="Provider" value={metadata.provider || 'unknown'} />
        <MetadataItem label="Model" value={metadata.model || 'unknown'} />
        <MetadataItem label="Latency" value={formatLatency(metadata.latencyMs)} />
        <MetadataItem label="Tokens" value={formatNumber(metadata.totalTokens)} />
      </div>

      <div className="mt-3 grid grid-cols-1 gap-2 text-xs md:grid-cols-3">
        <MetadataItem label="Prompt tokens" value={formatNumber(metadata.promptTokens)} />
        <MetadataItem label="Completion tokens" value={formatNumber(metadata.completionTokens)} />
        <MetadataItem label="Base URL" value={metadata.baseUrl || 'configured by backend'} />
      </div>

      {metadata.errorMessage && (
        <div className="mt-3 rounded border border-red-900/50 bg-red-950/30 p-3 text-xs text-red-200">
          <p className="font-medium">LLM API call failed</p>
          <p className="mt-1 text-red-200/90">{metadata.errorMessage}</p>
          <p className="mt-2 text-red-200/70">
            {metadata.retryable === null || metadata.retryable === undefined
              ? '后端未说明是否可重试。请检查对应环境变量和 provider 配置。'
              : metadata.retryable
                ? '该错误可能可重试；检查网络、限流或临时 provider 故障后再运行。'
                : '该错误通常不可通过重试解决；请先修正环境变量或 profile 配置。'}
          </p>
        </div>
      )}
    </div>
  )
}

function MetadataItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded border border-slate-800 bg-slate-900/40 p-2">
      <p className="text-slate-500">{label}</p>
      <p className="mt-1 truncate font-medium text-slate-200" title={value}>
        {value}
      </p>
    </div>
  )
}
