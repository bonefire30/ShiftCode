import { useMemo, useState } from 'react'
import type { FileState } from './types'

type Props = {
  fileStates: Record<string, FileState>
}

function statusClass(status: string | undefined) {
  if (status === 'done') return 'text-emerald-300 bg-emerald-500/10 border-emerald-800/60'
  if (status === 'failed') return 'text-red-300 bg-red-500/10 border-red-800/60'
  if (status === 'running' || status === 'in_progress') {
    return 'text-violet-200 bg-violet-500/10 border-violet-800/60'
  }
  return 'text-slate-400 bg-slate-800/70 border-slate-700'
}

function statusLabel(status: string | undefined) {
  if (status === 'done') return '完成'
  if (status === 'failed') return '失败'
  if (status === 'running' || status === 'in_progress') return '进行中'
  if (status === 'pending') return '待处理'
  return status || '未知'
}

function statusRank(status: string | undefined) {
  if (status === 'failed') return 0
  if (status === 'running' || status === 'in_progress') return 1
  if (status === 'pending' || !status) return 2
  if (status === 'done') return 3
  return 4
}

export function FileStatusPanel({ fileStates }: Props) {
  const entries = useMemo(
    () =>
      Object.entries(fileStates).sort(([pathA, stateA], [pathB, stateB]) => {
        const rankDiff = statusRank(stateA.status) - statusRank(stateB.status)
        if (rankDiff !== 0) return rankDiff
        return pathA.localeCompare(pathB)
      }),
    [fileStates]
  )
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const selectedEntry =
    (selectedPath && entries.find(([path]) => path === selectedPath)) || entries[0] || null
  const selectedState = selectedEntry?.[1]
  const total = entries.length
  const done = entries.filter(([, state]) => state.status === 'done').length
  const failed = entries.filter(([, state]) => state.status === 'failed').length
  const active = entries.filter(
    ([, state]) => state.status === 'running' || state.status === 'in_progress'
  ).length
  const pending = Math.max(0, total - done - failed - active)

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <h3 className="text-sm font-medium text-slate-200">文件状态</h3>
          <p className="text-xs text-slate-500 mt-1">
            每个 Java 文件的迁移状态和 Go 代码预览。
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-[11px]">
          <span className="rounded-full border border-slate-700 px-2 py-1 text-slate-400">
            总数 {total}
          </span>
          <span className="rounded-full border border-emerald-800/70 px-2 py-1 text-emerald-300">
            完成 {done}
          </span>
          <span className="rounded-full border border-red-800/70 px-2 py-1 text-red-300">
            失败 {failed}
          </span>
          <span className="rounded-full border border-slate-700 px-2 py-1 text-slate-400">
            待处理 {pending}
          </span>
        </div>
      </div>

      {entries.length === 0 ? (
        <div className="rounded border border-dashed border-slate-800 bg-slate-900/30 p-4 text-xs text-slate-500">
          开始迁移后，这里会显示每个文件的转换状态。
        </div>
      ) : (
        <div className="space-y-4">
          <div className="text-xs max-h-44 overflow-y-auto space-y-1 pr-1">
            {entries.map(([p, fs]) => {
              const selected = selectedEntry?.[0] === p
              return (
                <button
                  key={p}
                  type="button"
                  onClick={() => setSelectedPath(p)}
                  className={
                    selected
                      ? 'flex w-full items-center justify-between gap-3 rounded border border-violet-700/60 bg-violet-500/10 px-3 py-2 text-left text-slate-100'
                      : 'flex w-full items-center justify-between gap-3 rounded border border-transparent px-3 py-2 text-left text-slate-300 hover:border-slate-800 hover:bg-slate-900/60'
                  }
                >
                  <span className="min-w-0">
                    <span className="block truncate" title={p}>
                      {p.split('/').pop()}
                    </span>
                    <span className="block truncate text-[11px] text-slate-600" title={p}>
                      {p}
                    </span>
                  </span>
                  <span
                    className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] ${statusClass(
                      fs.status
                    )}`}
                  >
                    {statusLabel(fs.status)}
                  </span>
                </button>
              )
            })}
          </div>

          {selectedEntry && selectedState && (
            <div className="rounded border border-slate-800 bg-slate-900/30 p-3 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-medium text-slate-200" title={selectedEntry[0]}>
                    {selectedEntry[0]}
                  </p>
                  <p className="mt-1 text-slate-500">状态: {statusLabel(selectedState.status)}</p>
                </div>
                <span
                  className={`rounded-full border px-2 py-0.5 text-[10px] ${statusClass(
                    selectedState.status
                  )}`}
                >
                  {statusLabel(selectedState.status)}
                </span>
              </div>

              {selectedState.last_error_hint && (
                <div className="mt-3 rounded border border-red-900/50 bg-red-950/30 p-2 text-red-200">
                  {selectedState.last_error_hint}
                </div>
              )}

              {selectedState.errors && selectedState.errors.length > 0 && (
                <ul className="mt-3 list-disc space-y-1 pl-4 text-red-200">
                  {selectedState.errors.map((error, index) => (
                    <li key={`${index}-${error}`}>{error}</li>
                  ))}
                </ul>
              )}

              <div className="mt-3">
                <p className="mb-1 text-slate-500">Go 代码预览</p>
                <pre className="max-h-48 overflow-auto rounded bg-slate-950 p-3 text-[11px] text-slate-300 whitespace-pre-wrap">
                  {selectedState.go_code?.trim() || '暂无代码预览'}
                </pre>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
