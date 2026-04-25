type Props = {
  terminal: string
}

function lineTone(line: string) {
  const lower = line.toLowerCase()
  if (
    lower.includes('failed') ||
    lower.includes('fail') ||
    lower.includes('error') ||
    lower.includes('panic') ||
    lower.includes('undefined') ||
    lower.includes('cannot')
  ) {
    return 'border-red-900/50 bg-red-950/30 text-red-200'
  }
  if (lower.includes('pass') || lower.includes('succeeded') || lower.includes('ok:')) {
    return 'border-emerald-900/50 bg-emerald-950/20 text-emerald-200'
  }
  if (lower.includes('go build') || lower.includes('go test') || lower.includes('[reviewer]')) {
    return 'border-violet-900/50 bg-violet-950/20 text-violet-100'
  }
  return 'border-transparent text-slate-300'
}

function countMatches(lines: string[], pattern: RegExp) {
  return lines.filter((line) => pattern.test(line)).length
}

export function TerminalLogPanel({ terminal }: Props) {
  const trimmed = terminal.trim()
  const lines = trimmed ? terminal.split('\n') : []
  const failureCount = countMatches(lines, /failed|fail|error|panic|undefined|cannot/i)
  const passCount = countMatches(lines, /pass|succeeded|ok:/i)
  const buildMentions = countMatches(lines, /go build/i)
  const testMentions = countMatches(lines, /go test/i)

  const copyLog = () => {
    if (!terminal || !navigator.clipboard) return
    void navigator.clipboard.writeText(terminal)
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-medium text-slate-200">QA 终端</h3>
          <p className="mt-1 text-xs text-slate-500">
            build/test 输出和关键运行日志，失败信号会自动高亮。
          </p>
        </div>
        <button
          type="button"
          onClick={copyLog}
          disabled={!terminal}
          className="rounded border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
        >
          复制日志
        </button>
      </div>

      <div className="mb-3 flex flex-wrap gap-2 text-[11px]">
        <span className="rounded-full border border-slate-700 px-2 py-1 text-slate-400">
          行数 {lines.length}
        </span>
        <span
          className={
            failureCount > 0
              ? 'rounded-full border border-red-800/70 px-2 py-1 text-red-300'
              : 'rounded-full border border-slate-700 px-2 py-1 text-slate-400'
          }
        >
          失败信号 {failureCount}
        </span>
        <span
          className={
            passCount > 0
              ? 'rounded-full border border-emerald-800/70 px-2 py-1 text-emerald-300'
              : 'rounded-full border border-slate-700 px-2 py-1 text-slate-400'
          }
        >
          通过信号 {passCount}
        </span>
        <span className="rounded-full border border-slate-700 px-2 py-1 text-slate-400">
          build {buildMentions}
        </span>
        <span className="rounded-full border border-slate-700 px-2 py-1 text-slate-400">
          test {testMentions}
        </span>
      </div>

      {lines.length === 0 ? (
        <div className="rounded border border-dashed border-slate-800 bg-slate-900/30 p-4 text-xs text-slate-500">
          迁移开始后，这里会显示 build/test 输出和关键运行日志。
        </div>
      ) : (
        <div className="max-h-64 overflow-y-auto rounded border border-slate-800 bg-slate-950 p-2 font-mono text-[11px]">
          {lines.map((line, index) => (
            <div
              key={`${index}-${line}`}
              className={`rounded border px-2 py-1 whitespace-pre-wrap ${lineTone(line)}`}
            >
              {line || ' '}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
