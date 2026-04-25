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
import type { CaseItem, FileState, HitlPayload, StepRow } from './components/migration/types'

const API = ''

export function ProjectMigration() {
  const [cases, setCases] = useState<CaseItem[]>([])
  const [projectPath, setProjectPath] = useState('')
  const [analyze, setAnalyze] = useState<Record<string, unknown> | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [maxRepair, setMaxRepair] = useState(3)
  const [goModule, setGoModule] = useState('')
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
  }, [appendLog, goModule, maxRepair, projectPath, running, stop])

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
