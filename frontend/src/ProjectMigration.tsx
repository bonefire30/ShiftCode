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
  ConversionItem,
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
  const llmMetadata = extractLlmMetadata(lastState, llmProfile, {
    build: lastBuildOk,
    tests: lastTestOk,
    testGeneration: testGenOk,
    testQuality: testQualityOk,
  })

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
  selectedProfile: LlmEvaluationProfile,
  engineeringChecks: {
    build: boolean | null
    tests: boolean | null
    testGeneration: boolean | null
    testQuality: boolean | null
  }
): LlmEvaluationMetadata {
  const llm = asRecord(state?.llm_metadata) ?? asRecord(state?.llm) ?? asRecord(state?.model_metadata)
  const usage = asRecord(llm?.usage) ?? asRecord(llm?.token_usage) ?? asRecord(state?.token_usage)
  const error = asRecord(llm?.error) ?? asRecord(state?.llm_error)
  const profile = readString(llm?.profile) ?? readString(state?.llm_profile) ?? selectedProfile
  const engineeringStatus =
    asRecord(state?.engineeringStatus) ??
    asRecord(state?.engineering_status) ??
    asRecord(llm?.engineeringStatus) ??
    asRecord(llm?.engineering_status)

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
    statusReasons:
      readStringArray(llm?.statusReasons) ??
      readStringArray(llm?.status_reasons) ??
      readStringArray(state?.statusReasons) ??
      readStringArray(state?.status_reasons) ??
      [],
    gateFailures:
      readStringArray(llm?.gateFailures) ??
      readStringArray(llm?.gate_failures) ??
      readStringArray(state?.gateFailures) ??
      readStringArray(state?.gate_failures) ??
      [],
    statusCounts:
      readNumberRecord(state?.statusCounts) ??
      readNumberRecord(state?.status_counts) ??
      readNumberRecord(llm?.statusCounts) ??
      readNumberRecord(llm?.status_counts),
    projectStatusSummary:
      readNumberRecord(state?.projectStatusSummary) ??
      readNumberRecord(state?.project_status_summary) ??
      readNumberRecord(llm?.projectStatusSummary) ??
      readNumberRecord(llm?.project_status_summary),
    summaryCompleteness:
      readString(state?.summaryCompleteness) ??
      readString(state?.summary_completeness) ??
      readString(llm?.summaryCompleteness) ??
      readString(llm?.summary_completeness),
    engineeringStatus: {
      build:
        readString(engineeringStatus?.build) ??
        statusFromBoolean(engineeringChecks.build),
      tests:
        readString(engineeringStatus?.tests) ??
        readString(engineeringStatus?.test) ??
        statusFromBoolean(engineeringChecks.tests),
      testGeneration:
        readString(engineeringStatus?.testGeneration) ??
        readString(engineeringStatus?.test_generation) ??
        statusFromBoolean(engineeringChecks.testGeneration),
      testQuality:
        readString(engineeringStatus?.testQuality) ??
        readString(engineeringStatus?.test_quality) ??
        statusFromBoolean(engineeringChecks.testQuality),
    },
    testFailureReasons:
      readStringArray(state?.testFailureReasons) ??
      readStringArray(state?.test_failure_reasons) ??
      readStringArray(llm?.testFailureReasons) ??
      readStringArray(llm?.test_failure_reasons) ??
      deriveEngineeringFallback(
        readString(engineeringStatus?.tests) ?? readString(engineeringStatus?.test),
        'Test details unavailable; inspect reviewer logs or generated Go test output.'
      ),
    testGenerationReasons:
      readStringArray(state?.testGenerationReasons) ??
      readStringArray(state?.test_generation_reasons) ??
      readStringArray(llm?.testGenerationReasons) ??
      readStringArray(llm?.test_generation_reasons) ??
      deriveEngineeringFallback(
        readString(engineeringStatus?.testGeneration) ?? readString(engineeringStatus?.test_generation),
        'Test-generation details unavailable; inspect workflow logs for failed or partial generation.'
      ),
    recommendedNextActions:
      readStringArray(state?.recommendedNextActions) ??
      readStringArray(state?.recommended_next_actions) ??
      readStringArray(llm?.recommendedNextActions) ??
      readStringArray(llm?.recommended_next_actions) ??
      deriveRecommendedNextActions(
        readStringArray(llm?.statusReasons) ??
          readStringArray(llm?.status_reasons) ??
          readStringArray(state?.statusReasons) ??
          readStringArray(state?.status_reasons) ??
          [],
        readString(llm?.conversionStatus) ??
          readString(llm?.conversion_status) ??
          readString(state?.conversion_status),
        readStringArray(state?.testFailureReasons) ??
          readStringArray(state?.test_failure_reasons) ??
          [],
        readStringArray(state?.testGenerationReasons) ??
          readStringArray(state?.test_generation_reasons) ??
          []
      ),
    conversionItems:
      readConversionItems(state?.conversionItems) ??
      readConversionItems(state?.conversion_items) ??
      readConversionItems(llm?.conversionItems) ??
      readConversionItems(llm?.conversion_items) ??
      [],
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

function readStringArray(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null
  const items = value
    .map((item) => (typeof item === 'string' ? item.trim() : ''))
    .filter(Boolean)
  return items.length > 0 ? items : []
}

function readNumberRecord(value: unknown): Record<string, number> | undefined {
  const record = asRecord(value)
  if (!record) return undefined
  const entries = Object.entries(record).filter(
    (entry): entry is [string, number] => typeof entry[1] === 'number' && Number.isFinite(entry[1])
  )
  return entries.length > 0 ? Object.fromEntries(entries) : undefined
}

function readEngineeringStatus(value: unknown): ConversionItem['engineeringStatus'] | undefined {
  const record = asRecord(value)
  if (!record) return undefined
  return {
    build: readString(record.build),
    tests: readString(record.tests) ?? readString(record.test),
    testGeneration: readString(record.testGeneration) ?? readString(record.test_generation),
    testQuality: readString(record.testQuality) ?? readString(record.test_quality),
  }
}

function readConversionItems(value: unknown): ConversionItem[] | undefined {
  if (!Array.isArray(value)) return undefined
  const items: ConversionItem[] = []
  value.forEach((item) => {
    const record = asRecord(item)
    if (!record) return
    items.push({
      id: readString(record.id),
      path: readString(record.path),
      status: readString(record.status),
      semanticStatus: readString(record.semanticStatus) ?? readString(record.semantic_status),
      classifierStatus: readString(record.classifierStatus) ?? readString(record.classifier_status),
      reasons:
        readStringArray(record.reasons) ??
        readStringArray(record.statusReasons) ??
        readStringArray(record.status_reasons) ??
        [],
      testIssueReasons:
        readStringArray(record.testIssueReasons) ??
        readStringArray(record.test_issue_reasons) ??
        readStringArray(record.testFailureReasons) ??
        readStringArray(record.test_failure_reasons) ??
        [],
      testGenerationIssueReasons:
        readStringArray(record.testGenerationIssueReasons) ??
        readStringArray(record.test_generation_issue_reasons) ??
        readStringArray(record.testGenerationReasons) ??
        readStringArray(record.test_generation_reasons) ??
        [],
      engineeringStatus:
        readEngineeringStatus(record.engineeringStatus) ??
        readEngineeringStatus(record.engineering_status),
    })
  })
  return items
}

function readBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}

function statusFromBoolean(value: boolean | null) {
  if (value === null) return null
  return value ? 'success' : 'error'
}

function deriveEngineeringFallback(status: string | null, fallback: string): string[] {
  if (!status || status === 'success' || status === 'unknown') return []
  return [fallback]
}

function deriveRecommendedNextActions(
  statusReasons: string[],
  conversionStatus: string | null,
  testFailureReasons: string[],
  testGenerationReasons: string[]
): string[] {
  const actions = new Set<string>()

  if (conversionStatus === 'unsupported') {
    actions.add('Prioritize unsupported Java features first and plan manual migration for those areas.')
  }
  if (conversionStatus === 'partial') {
    actions.add('Treat the project output as a migration draft until partial items are resolved.')
  }
  if (conversionStatus === 'warning') {
    actions.add('Review caveats before relying on the generated Go in production paths.')
  }
  if (conversionStatus === 'error') {
    actions.add('Fix the blocking conversion error before reviewing downstream module results.')
  }

  if (statusReasons.some((reason) => /parser|config|default|error path/i.test(reason))) {
    actions.add('Review parser/config modules for default-value and error-path semantics.')
  }
  if (statusReasons.some((reason) => /stream/i.test(reason))) {
    actions.add('Rewrite stream-based logic manually into supported Go control flow before trusting behavior.')
  }
  if (statusReasons.some((reason) => /generic/i.test(reason))) {
    actions.add('Inspect generic-heavy code paths and replace them with explicit Go type strategies.')
  }
  if (testFailureReasons.length > 0) {
    actions.add('Inspect modules with failing tests before trusting project-level behavior.')
  }
  if (testGenerationReasons.length > 0) {
    actions.add('Review modules with partial or failed test generation to close migration blind spots.')
  }

  return Array.from(actions)
}

function classifyTestIssue(reason: string) {
  if (/generated[_ -]?test.*compile|compile failure/i.test(reason)) {
    return {
      label: 'generated_test_compile_failure',
      inspect: 'Inspect generated test files first; fix compile errors before judging converted code behavior.',
    }
  }
  if (/behavior mismatch|assertion|expected .* got|semantic contract/i.test(reason)) {
    return {
      label: 'generated_test_behavior_mismatch',
      inspect: 'Compare the generated test expectation with the intended Java behavior before changing conversion logic.',
    }
  }
  if (/harness|setup|fixture|environment/i.test(reason)) {
    return {
      label: 'missing_test_harness',
      inspect: 'Check missing test setup, fixtures, or environment assumptions before treating this as a conversion defect.',
    }
  }
  if (/unsupported/i.test(reason)) {
    return {
      label: 'unsupported_feature_blocks_test',
      inspect: 'Inspect unsupported feature reports first; test failures may be downstream of unsupported conversion gaps.',
    }
  }
  if (/ambiguous|unclear contract|unknown expected behavior/i.test(reason)) {
    return {
      label: 'ambiguous_semantic_contract',
      inspect: 'Clarify the expected Java semantic contract before deciding whether to change generated Go or tests.',
    }
  }
  if (/timeout|provider|rate limit|network|llm/i.test(reason)) {
    return {
      label: 'test_generation_timeout_or_provider_issue',
      inspect: 'Check provider/runtime stability and retry conditions before assuming a conversion-rule problem.',
    }
  }
  return {
    label: 'details_unavailable',
    inspect: 'Inspect workflow logs and generated tests for more context; the backend did not provide a narrower cause.',
  }
}

function buildInspectNextSteps(metadata: LlmEvaluationMetadata): string[] {
  const actions = new Set<string>()

  metadata.testFailureReasons?.forEach((reason) => {
    actions.add(classifyTestIssue(reason).inspect)
  })
  metadata.testGenerationReasons?.forEach((reason) => {
    actions.add(classifyTestIssue(reason).inspect)
  })
  metadata.conversionItems?.forEach((item) => {
    item.testIssueReasons?.forEach((reason) => {
      actions.add(classifyTestIssue(reason).inspect)
    })
    item.testGenerationIssueReasons?.forEach((reason) => {
      actions.add(classifyTestIssue(reason).inspect)
    })
  })

  return Array.from(actions)
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

function reviewGuidance(status: string | null | undefined) {
  if (status === 'warning') return 'Review caveats before relying on the generated Go.'
  if (status === 'partial') return 'Manual follow-up is required before treating this migration as complete.'
  if (status === 'unsupported') return 'Unsupported Java features were detected; plan manual migration for those areas.'
  if (status === 'error') return 'Conversion failed unexpectedly; inspect the error and rerun after fixing it.'
  if (status === 'success') return 'Supported-scope conversion passed with no reported caveats.'
  return 'Waiting for backend conversion status metadata.'
}

function hasNeedsReview(status: string | null | undefined) {
  return status === 'warning' || status === 'partial' || status === 'unsupported' || status === 'error'
}

function summaryLabel(summaryCompleteness: string | null | undefined) {
  if (summaryCompleteness === 'aggregate-only') return 'aggregate only'
  if (summaryCompleteness === 'incomplete') return 'incomplete'
  if (summaryCompleteness === 'complete') return 'complete'
  return null
}

function IssueReasonList({
  title,
  reasons,
}: {
  title: string
  reasons: string[]
}) {
  return (
    <div className="rounded border border-slate-800 bg-slate-900/30 p-3 text-xs">
      <p className="font-medium text-slate-200">{title}</p>
      <ul className="mt-2 space-y-2 text-slate-300">
        {reasons.map((reason, index) => {
          const issue = classifyTestIssue(reason)
          return (
            <li key={`${index}-${reason}`} className="rounded border border-slate-800 bg-slate-950/40 p-2">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <span className="text-slate-200">{reason}</span>
                <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-400">
                  {issue.label}
                </span>
              </div>
              <p className="mt-2 text-slate-500">Inspect next: {issue.inspect}</p>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function LlmEvaluationSummary({ metadata }: { metadata: LlmEvaluationMetadata }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-medium text-slate-200">LLM evaluation metadata</h3>
          <p className="mt-1 text-xs text-slate-500">
            API 调用状态、工程验证和转换状态是三个不同信号；build/test 通过不等于安全转换成功。
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

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs md:grid-cols-4">
        <MetadataItem label="Build validation" value={metadata.engineeringStatus?.build || 'unknown'} />
        <MetadataItem label="Test validation" value={metadata.engineeringStatus?.tests || 'unknown'} />
        <MetadataItem
          label="Test generation"
          value={metadata.engineeringStatus?.testGeneration || 'unknown'}
        />
        <MetadataItem label="Test quality" value={metadata.engineeringStatus?.testQuality || 'unknown'} />
      </div>

      <div className="mt-3 grid grid-cols-1 gap-2 text-xs md:grid-cols-3">
        <MetadataItem label="Prompt tokens" value={formatNumber(metadata.promptTokens)} />
        <MetadataItem label="Completion tokens" value={formatNumber(metadata.completionTokens)} />
        <MetadataItem label="Base URL" value={metadata.baseUrl || 'configured by backend'} />
      </div>

      {metadata.statusCounts && (
        <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
          {(['success', 'warning', 'partial', 'unsupported', 'error'] as const).map((status) => (
            <span
              key={status}
              className={`rounded-full border px-2 py-1 ${conversionStatusClass(status)}`}
            >
              {status} {metadata.statusCounts?.[status] ?? 0}
            </span>
          ))}
        </div>
      )}

      {metadata.projectStatusSummary && (
        <div className="mt-3 rounded border border-slate-800 bg-slate-900/30 p-3 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-medium text-slate-200">Project status summary</p>
            {summaryLabel(metadata.summaryCompleteness) && (
              <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-400">
                {summaryLabel(metadata.summaryCompleteness)}
              </span>
            )}
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
            {(['success', 'warning', 'partial', 'unsupported', 'error'] as const).map((status) => (
              <span
                key={`project-${status}`}
                className={`rounded-full border px-2 py-1 ${conversionStatusClass(status)}`}
              >
                {status} {metadata.projectStatusSummary?.[status] ?? 0}
              </span>
            ))}
          </div>
        </div>
      )}

      <div
        className={`mt-3 rounded border p-3 text-xs ${
          hasNeedsReview(metadata.conversionStatus)
            ? 'border-amber-900/50 bg-amber-950/20 text-amber-100'
            : 'border-slate-800 bg-slate-900/30 text-slate-300'
        }`}
      >
        <p className="font-medium">Conversion decision</p>
        <p className="mt-1 text-slate-300">{reviewGuidance(metadata.conversionStatus)}</p>
      </div>

      {metadata.statusReasons && metadata.statusReasons.length > 0 && (
        <div className="mt-3 rounded border border-slate-800 bg-slate-900/30 p-3 text-xs">
          <p className="font-medium text-slate-200">Status reasons</p>
          <ul className="mt-2 list-disc space-y-1 pl-4 text-slate-300">
            {metadata.statusReasons.map((reason, index) => (
              <li key={`${index}-${reason}`}>{reason}</li>
            ))}
          </ul>
        </div>
      )}

      {(metadata.testFailureReasons && metadata.testFailureReasons.length > 0) ||
      (metadata.testGenerationReasons && metadata.testGenerationReasons.length > 0) ? (
        <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
          {metadata.testFailureReasons && metadata.testFailureReasons.length > 0 && (
            <IssueReasonList
              title="Why tests are not fully passing"
              reasons={metadata.testFailureReasons}
            />
          )}
          {metadata.testGenerationReasons && metadata.testGenerationReasons.length > 0 && (
            <IssueReasonList
              title="Why test generation is partial"
              reasons={metadata.testGenerationReasons}
            />
          )}
        </div>
      ) : null}

      {buildInspectNextSteps(metadata).length > 0 && (
        <div className="mt-3 rounded border border-sky-900/50 bg-sky-950/20 p-3 text-xs text-sky-100">
          <p className="font-medium">What to inspect next</p>
          <ul className="mt-2 list-disc space-y-1 pl-4 text-sky-50/90">
            {buildInspectNextSteps(metadata).map((step, index) => (
              <li key={`${index}-${step}`}>{step}</li>
            ))}
          </ul>
        </div>
      )}

      {metadata.recommendedNextActions && metadata.recommendedNextActions.length > 0 && (
        <div className="mt-3 rounded border border-amber-900/50 bg-amber-950/20 p-3 text-xs text-amber-100">
          <p className="font-medium">Recommended next actions</p>
          <ul className="mt-2 list-disc space-y-1 pl-4 text-amber-50/90">
            {metadata.recommendedNextActions.map((action, index) => (
              <li key={`${index}-${action}`}>{action}</li>
            ))}
          </ul>
        </div>
      )}

      {metadata.conversionItems && metadata.conversionItems.length > 0 && (
        <div className="mt-3 rounded border border-slate-800 bg-slate-900/30 p-3 text-xs">
          <p className="font-medium text-slate-200">Items driving project status</p>
          <div className="mt-3 space-y-3">
            {metadata.conversionItems.map((item, index) => (
              <div key={`${item.id || item.path || 'item'}-${index}`} className="rounded border border-slate-800 bg-slate-950/40 p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-medium text-slate-200" title={item.path || item.id || 'unknown item'}>
                      {item.path || item.id || 'unknown item'}
                    </p>
                    {item.id && item.path && item.id !== item.path && (
                      <p className="mt-1 text-slate-500">{item.id}</p>
                    )}
                  </div>
                  <span className={`rounded-full border px-2 py-0.5 text-[10px] ${conversionStatusClass(item.status)}`}>
                    {item.status || 'unknown'}
                  </span>
                </div>
                {item.reasons && item.reasons.length > 0 && (
                  <ul className="mt-2 list-disc space-y-1 pl-4 text-slate-300">
                    {item.reasons.map((reason, reasonIndex) => (
                      <li key={`${reasonIndex}-${reason}`}>{reason}</li>
                    ))}
                  </ul>
                )}
                {(item.semanticStatus || item.classifierStatus) && (
                  <div className="mt-2 flex flex-wrap gap-2 text-[10px]">
                    {item.semanticStatus && (
                      <span className="rounded-full border border-slate-700 px-2 py-0.5 text-slate-300">
                        semantic {item.semanticStatus}
                      </span>
                    )}
                    {item.classifierStatus && (
                      <span className="rounded-full border border-slate-700 px-2 py-0.5 text-slate-300">
                        classifier {item.classifierStatus}
                      </span>
                    )}
                  </div>
                )}
                {(item.testIssueReasons && item.testIssueReasons.length > 0) ||
                (item.testGenerationIssueReasons && item.testGenerationIssueReasons.length > 0) ? (
                  <div className="mt-3 grid grid-cols-1 gap-2 lg:grid-cols-2">
                    {item.testIssueReasons && item.testIssueReasons.length > 0 && (
                      <IssueReasonList title="Test issues" reasons={item.testIssueReasons} />
                    )}
                    {item.testGenerationIssueReasons && item.testGenerationIssueReasons.length > 0 && (
                      <IssueReasonList
                        title="Generated test issues"
                        reasons={item.testGenerationIssueReasons}
                      />
                    )}
                  </div>
                ) : null}
                {item.engineeringStatus && (
                  <div className="mt-2 flex flex-wrap gap-2 text-[10px]">
                    <span className="rounded-full border border-slate-700 px-2 py-0.5 text-slate-300">
                      build {item.engineeringStatus.build || 'unknown'}
                    </span>
                    <span className="rounded-full border border-slate-700 px-2 py-0.5 text-slate-300">
                      tests {item.engineeringStatus.tests || 'unknown'}
                    </span>
                    <span className="rounded-full border border-slate-700 px-2 py-0.5 text-slate-300">
                      test gen {item.engineeringStatus.testGeneration || 'unknown'}
                    </span>
                    <span className="rounded-full border border-slate-700 px-2 py-0.5 text-slate-300">
                      test quality {item.engineeringStatus.testQuality || 'unknown'}
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {metadata.gateFailures && metadata.gateFailures.length > 0 && (
        <div className="mt-3 rounded border border-red-900/50 bg-red-950/30 p-3 text-xs text-red-200">
          <p className="font-medium">Gate failures</p>
          <ul className="mt-2 list-disc space-y-1 pl-4">
            {metadata.gateFailures.map((failure, index) => (
              <li key={`${index}-${failure}`}>{failure}</li>
            ))}
          </ul>
        </div>
      )}

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
