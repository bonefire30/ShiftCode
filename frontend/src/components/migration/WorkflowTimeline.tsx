import type { StepRow } from './types'
import { getWorkflowStage, WORKFLOW_STAGES } from './workflowStages'

type Props = {
  activeNode: string | null
  steps: StepRow[]
  repairRound: number | null
  lastBuildOk: boolean | null
  lastTestOk: boolean | null
  runStartedAt: number | null
  runEndedAt: number | null
  currentTime: number | null
}

function statusText(value: boolean | null) {
  if (value === null) return '未知'
  return value ? '通过' : '未通过'
}

function formatDuration(ms: number | null) {
  if (ms === null || ms < 0) return '—'
  const totalSeconds = Math.max(0, Math.round(ms / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes > 0) return `${minutes}m ${seconds}s`
  return `${seconds}s`
}

function firstStepTime(steps: StepRow[], node: string) {
  return steps.find((step) => step.node === node)?.timestamp ?? null
}

function nextDifferentStepTime(steps: StepRow[], node: string) {
  const firstIndex = steps.findIndex((step) => step.node === node)
  if (firstIndex < 0) return null
  return steps.slice(firstIndex + 1).find((step) => step.node !== node)?.timestamp ?? null
}

function stageDuration(
  steps: StepRow[],
  node: string,
  activeNode: string | null,
  runEndedAt: number | null
) {
  const start = firstStepTime(steps, node)
  if (start === null) return null
  const end = nextDifferentStepTime(steps, node) ?? (activeNode === node ? Date.now() : runEndedAt)
  if (end === null) return null
  return end - start
}

function spanDuration(steps: StepRow[], nodes: string[], runEndedAt: number | null) {
  const starts = nodes
    .map((node) => firstStepTime(steps, node))
    .filter((value): value is number => value !== null)
  if (starts.length === 0) return null
  const start = Math.min(...starts)
  const following = steps.find((step) => !nodes.includes(step.node) && step.timestamp > start)
  const end = following?.timestamp ?? runEndedAt
  if (end === null) return null
  return end - start
}

export function WorkflowTimeline({
  activeNode,
  steps,
  repairRound,
  lastBuildOk,
  lastTestOk,
  runStartedAt,
  runEndedAt,
  currentTime,
}: Props) {
  const currentStage = getWorkflowStage(activeNode)
  const visited = new Set(steps.map((step) => step.node))
  const migrationSucceeded = steps.length > 0 && !activeNode && lastBuildOk === true && lastTestOk === true
  const shouldTick = Boolean(runStartedAt && steps.length > 0 && !runEndedAt)
  const effectiveEnd = runEndedAt ?? (shouldTick ? currentTime : null)
  const totalDuration = runStartedAt && effectiveEnd ? effectiveEnd - runStartedAt : null
  const goGenerationDuration = spanDuration(
    steps,
    ['translate_modules', 'merge_all'],
    effectiveEnd
  )
  const testGenerationDuration = stageDuration(
    steps,
    'test_gen_modules',
    activeNode,
    effectiveEnd
  )
  const verificationDuration = stageDuration(steps, 'reviewer', activeNode, effectiveEnd)
  const repairDuration = spanDuration(
    steps,
    ['global_repair', 'test_gen_repair'],
    effectiveEnd
  )

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <h3 className="text-sm font-medium text-slate-200">迁移进度</h3>
          <p className="text-xs text-slate-500 mt-1">
            当前:{' '}
            <span className="text-slate-300">
              {migrationSucceeded
                ? '迁移完成'
                : currentStage?.label || activeNode || '等待开始'}
            </span>
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-[11px] text-slate-400">
          <span className="rounded-full border border-slate-700 px-2 py-1">
            总耗时 {formatDuration(totalDuration)}
          </span>
          <span className="rounded-full border border-slate-700 px-2 py-1">
            事件 {steps.length}
          </span>
          <span className="rounded-full border border-slate-700 px-2 py-1">
            修复轮次 {repairRound ?? 0}
          </span>
          <span
            className={
              lastBuildOk
                ? 'rounded-full border border-emerald-800/70 px-2 py-1 text-emerald-300'
                : 'rounded-full border border-slate-700 px-2 py-1'
            }
          >
            build {statusText(lastBuildOk)}
          </span>
          <span
            className={
              lastTestOk
                ? 'rounded-full border border-emerald-800/70 px-2 py-1 text-emerald-300'
                : 'rounded-full border border-slate-700 px-2 py-1'
            }
          >
            test {statusText(lastTestOk)}
          </span>
        </div>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <div className="rounded border border-slate-800 bg-slate-900/40 p-2">
          <p className="text-slate-500">Go 代码生成</p>
          <p className="mt-1 font-medium text-slate-200">{formatDuration(goGenerationDuration)}</p>
        </div>
        <div className="rounded border border-slate-800 bg-slate-900/40 p-2">
          <p className="text-slate-500">测试生成</p>
          <p className="mt-1 font-medium text-slate-200">{formatDuration(testGenerationDuration)}</p>
        </div>
        <div className="rounded border border-slate-800 bg-slate-900/40 p-2">
          <p className="text-slate-500">验证耗时</p>
          <p className="mt-1 font-medium text-slate-200">{formatDuration(verificationDuration)}</p>
        </div>
        <div className="rounded border border-slate-800 bg-slate-900/40 p-2">
          <p className="text-slate-500">修复耗时</p>
          <p className="mt-1 font-medium text-slate-200">{formatDuration(repairDuration)}</p>
        </div>
      </div>

      <ol className="space-y-3">
        {WORKFLOW_STAGES.map((stage, index) => {
          const isActive = activeNode === stage.id
          const isVisited = visited.has(stage.id)
          const isRepair = stage.id === 'global_repair' || stage.id === 'test_gen_repair'
          const isSkippedRepair = migrationSucceeded && isRepair && !isVisited
          const duration = stageDuration(steps, stage.id, activeNode, effectiveEnd)
          const markerClass = isActive
            ? 'border-violet-400 bg-violet-500 text-white shadow-[0_0_0_4px_rgba(139,92,246,0.12)]'
            : isVisited
              ? 'border-emerald-500 bg-emerald-500 text-white'
              : isSkippedRepair
                ? 'border-slate-700 bg-slate-900 text-slate-400'
              : 'border-slate-700 bg-slate-900 text-slate-500'
          const titleClass = isActive
            ? 'text-violet-200'
            : isVisited
              ? 'text-slate-200'
              : isSkippedRepair
                ? 'text-slate-400'
              : 'text-slate-500'

          return (
            <li key={stage.id} className="flex gap-3">
              <div className="flex flex-col items-center">
                <div
                  className={`flex h-6 w-6 items-center justify-center rounded-full border text-[11px] ${markerClass}`}
                >
                  {isVisited && !isActive ? '✓' : isSkippedRepair ? '—' : index + 1}
                </div>
                {index < WORKFLOW_STAGES.length - 1 && (
                  <div className="mt-1 h-full min-h-4 w-px bg-slate-800" />
                )}
              </div>
              <div className="min-w-0 pb-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className={`text-sm font-medium ${titleClass}`}>{stage.label}</p>
                  {isActive && (
                    <span className="rounded-full bg-violet-500/15 px-2 py-0.5 text-[10px] text-violet-200">
                      进行中 · 已运行 {formatDuration(duration)}
                    </span>
                  )}
                  {!isActive && isVisited && duration !== null && (
                    <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-300">
                      耗时 {formatDuration(duration)}
                    </span>
                  )}
                  {isRepair && isVisited && (
                    <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-200">
                      修复循环
                    </span>
                  )}
                  {isSkippedRepair && (
                    <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400">
                      无需执行
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-slate-500">{stage.description}</p>
              </div>
            </li>
          )
        })}
      </ol>

      <div className="mt-4 border-t border-slate-800 pt-3">
        <p className="text-xs text-slate-500 mb-2">最近事件</p>
        <ul className="text-xs space-y-1 max-h-24 overflow-y-auto text-slate-400">
          {steps.length === 0 && <li>暂无事件</li>}
          {steps.slice(-8).map((s, i) => {
            const stage = getWorkflowStage(s.node)
            return (
              <li key={`${s.at}-${s.node}-${i}`} className="flex justify-between gap-3">
                <span className="truncate">{stage?.label || s.node}</span>
                <span className="shrink-0 text-slate-600">{s.at}</span>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
