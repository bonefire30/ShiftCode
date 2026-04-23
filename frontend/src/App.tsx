import { useCallback, useEffect, useRef, useState } from 'react'
import { ProjectMigration } from './ProjectMigration'

type CaseItem = { id: string; name: string; path: string }

type StepPayload = {
  type: 'step'
  node: string
  state: Record<string, unknown>
}

type DonePayload = { type: 'done' }
type ErrorPayload = { type: 'error'; message: string }

type ChunkPayload = { type: 'chunk'; content: string }

type StreamEvent = StepPayload | DonePayload | ErrorPayload | ChunkPayload

/** Serialized from Python workflow (message history). */
type SerializedMessage = {
  role?: string
  content?: string
  /** Set for tool results (e.g. run_go_tests) when using LangChain ToolMessage with name. */
  name?: string
  tool_calls?: Array<{
    name?: string
    args?: Record<string, unknown>
    id?: string
  }>
  tool_call_id?: string
}

const API = ''

function App() {
  const [mainTab, setMainTab] = useState<'single' | 'project'>('single')
  const [cases, setCases] = useState<CaseItem[]>([])
  const [selectedPath, setSelectedPath] = useState('')
  const [useStub, setUseStub] = useState(false)
  /** When true, file-tool agent; when false, one-shot ```go``` legacy translator. */
  const [useAgentMode, setUseAgentMode] = useState(true)
  const [maxCalls, setMaxCalls] = useState(3)
  const [running, setRunning] = useState(false)
  const [activeNode, setActiveNode] = useState<string | null>(null)
  const [javaSource, setJavaSource] = useState('')
  const [goCode, setGoCode] = useState('')
  const [agentMessages, setAgentMessages] = useState<SerializedMessage[]>([])
  const [messagesCount, setMessagesCount] = useState<number | null>(null)
  const [workspaceDir, setWorkspaceDir] = useState('')
  const [streamingAssistant, setStreamingAssistant] = useState('')
  const [totalTokens, setTotalTokens] = useState<number | null>(null)
  const [translatorCalls, setTranslatorCalls] = useState(0)
  const [maxTranslatorCalls, setMaxTranslatorCalls] = useState(3)
  const [compileOk, setCompileOk] = useState<boolean | null>(null)
  const [testOk, setTestOk] = useState<boolean | null>(null)
  const [terminal, setTerminal] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [steps, setSteps] = useState<{ node: string; at: string }[]>([])
  const esRef = useRef<EventSource | null>(null)
  const useFreshChunkForNextStreamRef = useRef(false)
  const goCodePreRef = useRef<HTMLPreElement | null>(null)
  const agentStreamRef = useRef<HTMLDivElement | null>(null)
  /** Per-run: legacy = !useAgentMode at click time */
  const isLegacyRunRef = useRef(false)
  /** Deduplicate Agent run_go_tests tool output lines in QA terminal (repeated internal steps). */
  const loggedAgentRunGoTestsRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    fetch(`${API}/api/cases`)
      .then((r) => r.json())
      .then((data: CaseItem[]) => {
        setCases(data)
        if (data.length) {
          setSelectedPath((prev) => prev || data[0].path)
        }
      })
      .catch(() =>
        setError(
          '无法连接后端。请先运行: uvicorn server:app --host 127.0.0.1 --port 8000'
        )
      )
  }, [])

  useEffect(() => {
    if (!selectedPath) {
      setJavaSource('')
      return
    }
    const q = new URLSearchParams({ case: selectedPath })
    const ac = new AbortController()
    fetch(`${API}/api/case/source?${q.toString()}`, { signal: ac.signal })
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status))
        return r.json() as Promise<{ content: string }>
      })
      .then((d) => setJavaSource(d.content))
      .catch(() => {
        if (!ac.signal.aborted) setJavaSource('')
      })
    return () => ac.abort()
  }, [selectedPath])

  useEffect(() => {
    const el = goCodePreRef.current
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  }, [goCode])

  useEffect(() => {
    const el = agentStreamRef.current
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  }, [agentMessages, streamingAssistant])

  const appendLog = useCallback((line: string) => {
    setTerminal((t) => t + (t ? '\n' : '') + line)
  }, [])

  const stop = useCallback(() => {
    esRef.current?.close()
    esRef.current = null
    setRunning(false)
  }, [])

  const start = useCallback(() => {
    if (!selectedPath || running) return
    setError(null)
    setTerminal('')
    setSteps([])
    setAgentMessages([])
    setMessagesCount(null)
    setWorkspaceDir('')
    setStreamingAssistant('')
    setTotalTokens(null)
    setActiveNode('translator')
    setGoCode('')
    useFreshChunkForNextStreamRef.current = false
    setCompileOk(null)
    setTestOk(null)
    setRunning(true)
    isLegacyRunRef.current = !useAgentMode
    loggedAgentRunGoTestsRef.current = new Set()
    appendLog('--- 翻译官 开始 ---')

    const params = new URLSearchParams({
      case: selectedPath,
      use_stub: useStub ? 'true' : 'false',
      max_calls: String(maxCalls),
      use_legacy: !useAgentMode ? 'true' : 'false',
    })
    const url = `${API}/api/migrate/stream?${params.toString()}`
    const es = new EventSource(url)
    esRef.current = es

    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as StreamEvent
        if (data.type === 'error') {
          setError(data.message)
          stop()
          return
        }
        if (data.type === 'done') {
          setActiveNode(null)
          stop()
          return
        }
        if (data.type === 'chunk') {
          setActiveNode('translator')
          const c = (data as ChunkPayload).content
          if (isLegacyRunRef.current) {
            if (useFreshChunkForNextStreamRef.current) {
              useFreshChunkForNextStreamRef.current = false
              setGoCode(c)
            } else {
              setGoCode((prev) => prev + c)
            }
          } else {
            setStreamingAssistant((p) => p + c)
          }
          return
        }
        if (data.type === 'step') {
          const s = data.state
          setStreamingAssistant('')
          if (data.node === 'translator_internal') {
            setActiveNode('translator')
          } else {
            setActiveNode(data.node)
          }
          if (data.node !== 'translator_internal') {
            setSteps((prev) => [
              ...prev,
              { node: data.node, at: new Date().toLocaleTimeString() },
            ])
          }
          if (Array.isArray(s.messages)) {
            setAgentMessages(s.messages as SerializedMessage[])
          }
          if (typeof s.messages_count === 'number') {
            setMessagesCount(s.messages_count)
          }
          if (typeof s.workspace_dir === 'string') {
            setWorkspaceDir(s.workspace_dir)
          }
          if (typeof s.total_tokens === 'number') {
            setTotalTokens(s.total_tokens)
          }
          if (typeof s.java_source === 'string') setJavaSource(s.java_source)
          if (typeof s.go_code === 'string') setGoCode(s.go_code)
          if (typeof s.translator_calls === 'number')
            setTranslatorCalls(s.translator_calls)
          if (typeof s.max_translator_calls === 'number')
            setMaxTranslatorCalls(s.max_translator_calls)
          if (typeof s.compile_ok === 'boolean') setCompileOk(s.compile_ok)
          if (typeof s.test_ok === 'boolean') setTestOk(s.test_ok)

          if (data.node === 'qa') {
            if (isLegacyRunRef.current) {
              if (!s.compile_ok || !s.test_ok) {
                setGoCode('')
                useFreshChunkForNextStreamRef.current = true
              }
            }
            const build = (s.build_log as string) || ''
            const testl = (s.test_log as string) || ''
            const repair = (s.last_repair_error as string) || ''
            if (build || testl || repair) {
              appendLog('--- QA (图节点 go build / go test) ---')
              if (build) appendLog('go build:\n' + build)
              if (testl) appendLog('go test:\n' + testl)
              if (repair && !s.compile_ok) appendLog('repair hint:\n' + repair)
            }
          } else if (data.node === 'translator_internal') {
            if (!isLegacyRunRef.current && Array.isArray(s.messages)) {
              for (const m of s.messages as SerializedMessage[]) {
                if (m.role !== 'tool') continue
                const c = String(m.content ?? '')
                const isRunGo =
                  m.name === 'run_go_tests' ||
                  (!m.name &&
                    /^(OK: all tests passed|FAILED: compile_ok=)/.test(
                      c.trim()
                    ))
                if (!isRunGo) continue
                const k = c.length > 8000 ? c.slice(0, 8000) + '…' : c
                if (loggedAgentRunGoTestsRef.current.has(k)) continue
                loggedAgentRunGoTestsRef.current.add(k)
                appendLog('--- Agent 沙箱 (run_go_tests) ---\n' + c)
              }
            }
          } else if (data.node === 'translator') {
            if (!isLegacyRunRef.current && Array.isArray(s.messages)) {
              for (const m of s.messages as SerializedMessage[]) {
                if (m.role !== 'tool') continue
                const c = String(m.content ?? '')
                const isRunGo =
                  m.name === 'run_go_tests' ||
                  (!m.name &&
                    /^(OK: all tests passed|FAILED: compile_ok=)/.test(
                      c.trim()
                    ))
                if (!isRunGo) continue
                const k = c.length > 8000 ? c.slice(0, 8000) + '…' : c
                if (loggedAgentRunGoTestsRef.current.has(k)) continue
                loggedAgentRunGoTestsRef.current.add(k)
                appendLog('--- Agent 沙箱 (run_go_tests) ---\n' + c)
              }
            }
            appendLog(
              `--- 翻译 / Agent (第 ${s.translator_calls ?? '?'} 轮) 结束 ---`
            )
          } else if (data.node === 'reflect') {
            appendLog('--- 反思 (learnings) ---')
          }
        }
      } catch {
        appendLog('(parse error) ' + ev.data)
      }
    }

    es.onerror = () => {
      appendLog('(EventSource 连接结束或出错)')
      stop()
    }
  }, [
    selectedPath,
    useStub,
    maxCalls,
    useAgentMode,
    appendLog,
    stop,
  ])

  return (
    <div className="min-h-screen flex flex-col p-4 max-w-[1920px] mx-auto">
      <header className="border-b border-slate-800 pb-4 mb-4">
        <h1 className="text-xl font-semibold text-white tracking-tight">
          多智能体代码迁移
          <span className="text-slate-500 font-normal ml-2">Java → Go</span>
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Agent 模式显示工具循环与消息；单轮模式流式拼接到 <code>output.go</code>。项目
          模式：多文件依赖图与批次迁移。
        </p>
        <div className="flex gap-2 mt-3">
          <button
            type="button"
            onClick={() => setMainTab('single')}
            className={`px-3 py-1.5 rounded text-sm ${
              mainTab === 'single'
                ? 'bg-violet-600 text-white'
                : 'bg-slate-800 text-slate-400'
            }`}
          >
            单文件迁移
          </button>
          <button
            type="button"
            onClick={() => setMainTab('project')}
            className={`px-3 py-1.5 rounded text-sm ${
              mainTab === 'project'
                ? 'bg-violet-600 text-white'
                : 'bg-slate-800 text-slate-400'
            }`}
          >
            项目迁移 (Agent Team)
          </button>
        </div>
      </header>

      {mainTab === 'project' && (
        <div className="mb-6 border border-slate-800 rounded-lg p-4 bg-slate-900/20">
          <ProjectMigration />
        </div>
      )}

      {mainTab === 'single' && (
        <>
      <div className="flex flex-wrap gap-3 items-end mb-4">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-slate-400">测试用例</span>
          <select
            className="bg-slate-900 border border-slate-700 rounded px-3 py-2 min-w-[280px]"
            value={selectedPath}
            onChange={(e) => setSelectedPath(e.target.value)}
            disabled={running}
          >
            {cases.length === 0 && <option value="">（无用例）</option>}
            {cases.map((c) => (
              <option key={c.id} value={c.path}>
                {c.name} — {c.path}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={useStub}
            onChange={(e) => setUseStub(e.target.checked)}
            disabled={running}
            className="rounded border-slate-600"
          />
          Stub（golden_output.go）
        </label>
        <label className="flex items-center gap-2 text-sm cursor-pointer" title="关闭则使用旧版单轮输出 ```go```">
          <input
            type="checkbox"
            checked={useAgentMode}
            onChange={(e) => setUseAgentMode(e.target.checked)}
            disabled={running || useStub}
            className="rounded border-slate-600"
          />
          Agent 模式（工具 + run_go_tests）
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-slate-400">最大重试次数</span>
          <input
            type="number"
            min={1}
            max={20}
            value={maxCalls}
            onChange={(e) => setMaxCalls(Number(e.target.value) || 3)}
            disabled={running}
            className="w-20 bg-slate-900 border border-slate-700 rounded px-2 py-2"
          />
        </label>
        <button
          type="button"
          onClick={start}
          disabled={running || !selectedPath}
          className="px-4 py-2 rounded bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-sm font-medium"
        >
          开始迁移
        </button>
        <button
          type="button"
          onClick={stop}
          disabled={!running}
          className="px-4 py-2 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-sm"
        >
          停止
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded border border-red-900/50 bg-red-950/40 text-red-200 text-sm">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 flex-1 min-h-[calc(100vh-220px)]">
        <aside className="xl:col-span-3 flex flex-col gap-3 min-h-0">
          <h2 className="text-sm font-medium text-slate-400">工作流</h2>
          <div className="flex flex-col gap-2">
            <NodeCard
              label="翻译官 / Agent"
              active={activeNode === 'translator'}
            />
            <div className="text-center text-slate-600 text-xs">↓</div>
            <NodeCard
              label="QA (go build / test)"
              active={activeNode === 'qa'}
            />
            <div className="text-center text-slate-600 text-xs">↓</div>
            <NodeCard label="反思 (learnings)" active={activeNode === 'reflect'} />
          </div>
          <div className="text-xs text-slate-500 space-y-1">
            <div>
              重试: {translatorCalls} / 上限 {maxTranslatorCalls}
              {compileOk !== null && (
                <span className="ml-2">
                  编译 {compileOk ? 'OK' : 'FAIL'} / 单测{' '}
                  {testOk === true
                    ? 'OK'
                    : testOk === false
                      ? 'FAIL'
                      : '-'}
                </span>
              )}
            </div>
            {totalTokens != null && (
              <div>Token (累计): {totalTokens}</div>
            )}
            {useAgentMode && messagesCount != null && (
              <div>
                消息(后端 count): {messagesCount}，本页展示: {agentMessages.length}
              </div>
            )}
            {workspaceDir && (
              <div
                className="text-[10px] text-slate-600 break-all"
                title={workspaceDir}
              >
                工作区: {workspaceDir}
              </div>
            )}
          </div>
          <ul className="text-xs text-slate-500 space-y-1 max-h-24 overflow-y-auto">
            {steps.map((s, i) => (
              <li key={i}>
                [{s.at}] {s.node}
              </li>
            ))}
          </ul>
          <div className="flex flex-col min-h-0 flex-1">
            <h3 className="text-xs font-medium text-slate-500 mb-1">source.java</h3>
            <pre className="flex-1 min-h-[120px] text-xs p-3 rounded-lg bg-slate-900/80 border border-slate-800 overflow-auto text-slate-300 font-mono whitespace-pre-wrap break-all">
              {javaSource || '（选择用例后加载）'}
            </pre>
          </div>
        </aside>

        <section className="xl:col-span-5 flex flex-col min-h-0 gap-2">
          <h3 className="text-xs font-medium text-slate-500">Agent 消息 / 工具流</h3>
          <div
            ref={agentStreamRef}
            className="flex-1 min-h-[200px] max-h-[70vh] overflow-y-auto rounded-lg border border-slate-800 bg-slate-950/50 p-3 space-y-2"
          >
            {!useAgentMode && (
              <p className="text-xs text-slate-500">
                单轮模式：大模型流式输出显示在右侧 <code>output.go</code>，此处不展示分步消息。
              </p>
            )}
            {useAgentMode && agentMessages.length === 0 && !streamingAssistant && (
              <p className="text-xs text-slate-500">
                （运行中或等待；步骤结束后由后端同步消息历史）
              </p>
            )}
            {useAgentMode &&
              agentMessages.map((m, i) => (
                <MessageBlock key={i} m={m} index={i} />
              ))}
            {useAgentMode && streamingAssistant && (
              <div className="rounded border border-cyan-900/50 bg-cyan-950/20 p-2 text-xs">
                <div className="text-cyan-400/80 mb-1">流式 (当前轮)</div>
                <pre className="whitespace-pre-wrap text-slate-200 font-mono break-all max-h-40 overflow-y-auto">
                  {streamingAssistant}
                </pre>
              </div>
            )}
          </div>
          <div className="flex flex-col min-h-[120px] max-h-40">
            <h3 className="text-xs font-medium text-slate-500 mb-1">日志 / QA 摘要</h3>
            <pre className="flex-1 text-xs p-2 rounded-lg bg-black/50 border border-slate-800 overflow-auto text-amber-100/90 font-mono whitespace-pre-wrap">
              {terminal || '（无）'}
            </pre>
          </div>
        </section>

        <section className="xl:col-span-4 flex flex-col min-h-0 gap-2">
          <h3 className="text-xs font-medium text-slate-500">output.go（与沙箱一致）</h3>
          <pre
            ref={goCodePreRef}
            className="flex-1 min-h-[200px] text-xs p-3 rounded-lg bg-slate-900/80 border border-slate-800 overflow-auto text-emerald-200/90 font-mono whitespace-pre-wrap break-all"
          >
            {goCode || (useAgentMode ? '（等待步骤结束写入）' : '（等待流式或步骤）')}
          </pre>
        </section>
      </div>
    </>
    )}
    </div>
  )
}

function NodeCard({ label, active }: { label: string; active: boolean }) {
  return (
    <div
      className={`rounded-lg border px-3 py-2 text-sm transition-colors ${
        active
          ? 'border-violet-500 bg-violet-950/50 text-violet-200 ring-1 ring-violet-500/30'
          : 'border-slate-700 bg-slate-900/50 text-slate-400'
      }`}
    >
      {active && (
        <span className="inline-block w-2 h-2 rounded-full bg-violet-400 mr-2 animate-pulse" />
      )}
      {label}
    </div>
  )
}

function MessageBlock({
  m,
  index: _i,
}: {
  m: SerializedMessage
  index: number
}) {
  const role = (m.role || 'unknown').toLowerCase()
  const content = typeof m.content === 'string' ? m.content : String(m.content ?? '')

  if (role === 'system') {
    return (
      <details className="text-xs border border-slate-800 rounded bg-slate-900/30">
        <summary className="cursor-pointer text-slate-500 px-2 py-1">
          system
        </summary>
        <pre className="p-2 text-slate-400 whitespace-pre-wrap break-all max-h-32 overflow-y-auto">
          {content.slice(0, 20_000)}
        </pre>
      </details>
    )
  }

  if (role === 'user') {
    return (
      <div className="text-xs border-l-2 border-slate-600 pl-2">
        <div className="text-slate-500 mb-0.5">user</div>
        <pre className="whitespace-pre-wrap text-slate-300 break-all max-h-40 overflow-y-auto">
          {content.slice(0, 20_000)}
        </pre>
      </div>
    )
  }

  if (role === 'tool') {
    const title = m.name
      ? `tool: ${m.name}${m.tool_call_id ? ` (${m.tool_call_id})` : ''}`
      : m.tool_call_id
        ? `tool reply (${m.tool_call_id})`
        : 'tool'
    return (
      <div className="text-xs">
        <div className="text-amber-500/90 mb-0.5 font-medium">{title}</div>
        <ToolResultBody text={content} />
      </div>
    )
  }

  if (role === 'assistant') {
    const tcs = m.tool_calls || []
    return (
      <div className="text-xs border border-slate-700/80 rounded-lg p-2 bg-slate-900/40">
        <div className="text-violet-300/90 mb-1">assistant</div>
        {tcs.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-2">
            {tcs.map((tc, j) => (
              <span
                key={j}
                className="px-1.5 py-0.5 rounded bg-violet-950 text-violet-200 text-[10px] font-mono"
              >
                {tc.name || 'tool'}
              </span>
            ))}
          </div>
        )}
        {content && (
          <pre className="whitespace-pre-wrap text-slate-200 break-all max-h-32 overflow-y-auto">
            {content}
          </pre>
        )}
      </div>
    )
  }

  return (
    <div className="text-xs text-slate-500 border border-slate-800 p-1 rounded">
      {String(role)}: {content.slice(0, 500)}
    </div>
  )
}

function ToolResultBody({ text }: { text: string }) {
  if (text.length < 500) {
    return (
      <pre className="p-2 rounded bg-black/30 text-slate-300 font-mono text-[11px] whitespace-pre-wrap break-all max-h-48 overflow-y-auto">
        {text}
      </pre>
    )
  }
  return (
    <details
      className="rounded bg-black/30 border border-slate-800"
      open={text.length < 2000}
    >
      <summary className="cursor-pointer px-2 py-1 text-amber-200/80 text-[11px]">
        展开长输出 ({text.length} 字符)
      </summary>
      <pre className="p-2 text-slate-300 font-mono text-[11px] whitespace-pre-wrap break-all max-h-64 overflow-y-auto">
        {text.slice(0, 50_000)}
      </pre>
    </details>
  )
}

export default App
