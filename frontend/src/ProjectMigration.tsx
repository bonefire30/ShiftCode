import { useCallback, useEffect, useRef, useState } from 'react'

const API = ''

type CaseItem = { id: string; name: string; path: string }

type FileState = {
  status?: string
  go_code?: string
  last_error_hint?: string
  errors?: string[]
}

type StepRow = { node: string; at: string }

type HitlPayload = {
  thread_id?: string
  question?: string
  key?: string
  type?: string
}

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
          stop()
          return
        }
        if (data.type === 'done') {
          setActiveNode(null)
          appendLog('--- 流结束 ---')
          stop()
          return
        }
        if (data.type === 'step' && data.node) {
          const nodeName = data.node
          setActiveNode(nodeName)
          setSteps((prev) => [
            ...prev,
            { node: nodeName, at: new Date().toLocaleTimeString() },
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

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-500">
        多文件：架构师建依赖图 → 批次自底向上翻译 → go build
        闭环修复。路径须位于仓库内。
      </p>
      <div className="flex flex-wrap gap-3 items-end">
        <div className="flex flex-col gap-1 text-sm min-w-[320px]">
          <span className="text-slate-400">项目目录 (benchmark 用例，与单文件页一致)</span>
          {cases.length > 0 ? (
            <select
              className="bg-slate-900 border border-slate-700 rounded px-3 py-2 min-w-[280px] w-full"
              value={
                cases.some((c) => c.path === projectPath) ? projectPath : '__manual__'
              }
              onChange={(e) => {
                const v = e.target.value
                if (v && v !== '__manual__') setProjectPath(v)
              }}
              disabled={running}
            >
              {cases.map((c) => (
                <option key={c.id} value={c.path}>
                  {c.name} — {c.path}
                </option>
              ))}
              <option value="__manual__">手动输入（见下方）</option>
            </select>
          ) : (
            <p className="text-xs text-amber-500/90">
              未扫描到 benchmark 用例，请手填「自定义路径」。
            </p>
          )}
          <label className="text-xs text-slate-500 mt-1 block">
            自定义路径 (相对仓库根，可与上方面板相同)
            <input
              className="mt-1 block w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-slate-200"
              value={projectPath}
              onChange={(e) => setProjectPath(e.target.value)}
              disabled={running}
              placeholder="例如 benchmark_dataset/..."
            />
          </label>
        </div>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-slate-400">最大修复轮数 / 次失败</span>
          <input
            type="number"
            min={1}
            max={20}
            className="w-20 bg-slate-900 border border-slate-700 rounded px-2 py-2"
            value={maxRepair}
            onChange={(e) => setMaxRepair(Number(e.target.value) || 3)}
            disabled={running}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm min-w-[200px]">
          <span className="text-slate-400">go module (可选)</span>
          <input
            className="bg-slate-900 border border-slate-700 rounded px-3 py-2"
            value={goModule}
            onChange={(e) => setGoModule(e.target.value)}
            disabled={running}
            placeholder="m.example/pkg"
          />
        </label>
        <button
          type="button"
          onClick={runAnalyze}
          disabled={analyzing || !projectPath}
          className="px-4 py-2 rounded bg-slate-700 hover:bg-slate-600 text-sm"
        >
          {analyzing ? '分析中…' : '仅扫描/依赖图'}
        </button>
        <button
          type="button"
          onClick={startMigrate}
          disabled={running}
          className="px-4 py-2 rounded bg-violet-600 hover:bg-violet-500 text-sm text-white font-medium"
        >
          开始项目迁移
        </button>
        <button
          type="button"
          onClick={stop}
          disabled={!running}
          className="px-4 py-2 rounded bg-slate-700 text-sm"
        >
          停止
        </button>
      </div>

      {(testGenExpected !== null ||
        testGenGenerated !== null ||
        testGenFailures.length > 0 ||
        testGenWarnings.length > 0) && (
        <div className="p-3 rounded border border-slate-800 bg-slate-900/30 text-xs text-slate-300 space-y-2">
          <div className="flex flex-wrap gap-4">
            <span>
              test gen:{' '}
              <span className={testGenOk ? 'text-emerald-400' : 'text-amber-400'}>
                {testGenOk === null ? '?' : testGenOk ? 'ok' : 'needs repair'}
              </span>
            </span>
            <span>expected: {testGenExpected ?? '?'}</span>
            <span>generated: {testGenGenerated ?? '?'}</span>
            <span>
              quality:{' '}
              <span className={testQualityOk ? 'text-emerald-400' : 'text-amber-400'}>
                {testQualityOk === null ? '?' : testQualityOk ? 'ok' : 'needs repair'}
              </span>
            </span>
          </div>
          {testGenFailures.length > 0 && (
            <div className="space-y-1">
              {testGenFailures.map((failure, idx) => (
                <div key={`${idx}-${failure}`} className="text-red-300">
                  {failure}
                </div>
              ))}
            </div>
          )}
          {testGenWarnings.length > 0 && (
            <div className="space-y-1">
              {testGenWarnings.map((warning, idx) => (
                <div key={`${idx}-${warning}`} className="text-amber-300">
                  {warning}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="p-3 rounded border border-red-900/50 bg-red-950/40 text-red-200 text-sm">
          {error}
        </div>
      )}

      {hitl && (
        <div className="p-4 rounded border border-amber-700/50 bg-amber-950/30 text-amber-100">
          <p className="text-sm font-medium">需要人工决策 (HITL)</p>
          <p className="text-xs mt-1">{hitl.question || hitl.type}</p>
          <div className="flex gap-2 mt-2">
            <button
              type="button"
              className="px-3 py-1 rounded bg-amber-700"
              onClick={() => sendHitl('accept_defaults')}
            >
              接受默认
            </button>
            <button
              type="button"
              className="px-3 py-1 rounded bg-slate-600"
              onClick={() => sendHitl('skip')}
            >
              跳过
            </button>
          </div>
        </div>
      )}

      {analyze && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 text-xs text-slate-300">
          <div>
            <h3 className="text-slate-400 mb-1">文件 ({(analyze.java_files as string[])?.length ?? 0})</h3>
            <ul className="list-disc pl-4 max-h-40 overflow-y-auto">
              {((analyze.java_files as string[]) || []).map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            <h3 className="text-slate-400 mt-2 mb-1">框架标志</h3>
            <p>{(analyze.framework_flags as string[])?.join(', ') || '无'}</p>
          </div>
          <div>
            <h3 className="text-slate-400 mb-1">依赖图 (邻接)</h3>
            <pre className="p-2 bg-slate-900/50 rounded max-h-48 overflow-auto whitespace-pre-wrap">
              {JSON.stringify(analyze.dependency_graph, null, 2)}
            </pre>
          </div>
          <div className="lg:col-span-2">
            <h3 className="text-slate-400 mb-1">拓扑批次 (并行层)</h3>
            <pre className="p-2 bg-slate-900/50 rounded max-h-40 overflow-auto">
              {JSON.stringify(analyze.translation_batches, null, 2)}
            </pre>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 min-h-[320px]">
        <div>
          <h3 className="text-sm text-slate-400 mb-2">工作流</h3>
          <p className="text-xs text-slate-500 mb-2">当前: {activeNode || '—'}</p>
          <ul className="text-xs space-y-1 max-h-32 overflow-y-auto text-slate-400">
            {steps.map((s, i) => (
              <li key={i}>
                {s.at} {s.node}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="text-sm text-slate-400 mb-2">文件状态</h3>
          <div className="text-xs max-h-40 overflow-y-auto space-y-1">
            {Object.entries(fileStates).map(([p, fs]) => (
              <div key={p} className="flex gap-2 text-slate-300">
                <span title={p}>
                  {p.split('/').pop()}{' '}
                </span>
                <span
                  className={
                    fs.status === 'done'
                      ? 'text-emerald-400'
                      : fs.status === 'failed'
                        ? 'text-red-400'
                        : 'text-slate-500'
                  }
                >
                  {fs.status || '?'}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {lastState &&
        typeof lastState.go_output_dir === 'string' &&
        lastState.go_output_dir && (
        <p className="text-xs text-slate-500">
          Go 输出: {lastState.go_output_dir}
        </p>
      )}

      <div>
        <h3 className="text-sm text-slate-400 mb-2">QA 终端 (go build 日志等)</h3>
        <pre className="p-3 rounded bg-slate-950 border border-slate-800 text-xs text-slate-300 whitespace-pre-wrap min-h-[120px] max-h-[200px] overflow-y-auto">
          {terminal || '（空）'}
        </pre>
      </div>
    </div>
  )
}
