import type { HitlPayload } from './types'

type Props = {
  hitl: HitlPayload | null
  onDecision: (decision: string) => void
}

export function HitlDecisionPanel({ hitl, onDecision }: Props) {
  if (!hitl) return null

  return (
    <div className="rounded-lg border border-amber-700/50 bg-amber-950/30 p-4 text-amber-100 shadow-[0_0_0_1px_rgba(251,191,36,0.04)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium">需要人工决策</p>
            <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] text-amber-200">
              HITL
            </span>
          </div>
          <p className="mt-1 text-xs text-amber-100/80">
            检测到项目可能包含框架或运行时特征，需要选择迁移策略后继续。
          </p>
        </div>
        <span className="rounded-full border border-amber-700/50 px-2 py-1 text-[11px] text-amber-200">
          建议接受默认
        </span>
      </div>

      <div className="mt-3 rounded border border-amber-800/50 bg-amber-950/40 p-3 text-xs text-amber-50/90">
        {hitl.question || hitl.type || '请选择后续迁移策略。'}
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <button
          type="button"
          className="rounded-lg border border-amber-500/60 bg-amber-500/15 p-3 text-left transition hover:border-amber-400 hover:bg-amber-500/20"
          onClick={() => onDecision('accept_defaults')}
        >
          <span className="flex items-center justify-between gap-3">
            <span className="text-sm font-medium text-amber-50">接受默认策略</span>
            <span className="rounded-full bg-amber-400 px-2 py-0.5 text-[10px] font-medium text-amber-950">
              推荐
            </span>
          </span>
          <span className="mt-2 block text-xs leading-5 text-amber-100/75">
            使用系统推荐的框架处理方式继续迁移。适合大多数标准项目和 benchmark 用例。
          </span>
        </button>
        <button
          type="button"
          className="rounded-lg border border-slate-700 bg-slate-950/40 p-3 text-left transition hover:border-slate-600 hover:bg-slate-900/70"
          onClick={() => onDecision('skip')}
        >
          <span className="text-sm font-medium text-slate-100">跳过额外策略</span>
          <span className="mt-2 block text-xs leading-5 text-slate-400">
            不应用额外框架适配，直接继续迁移。可能导致生成代码缺少部分框架语义。
          </span>
        </button>
      </div>

      {(hitl.key || hitl.type || hitl.thread_id) && (
        <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-amber-100/50">
          {hitl.type && <span>type: {hitl.type}</span>}
          {hitl.key && <span>key: {hitl.key}</span>}
          {hitl.thread_id && <span>thread: {hitl.thread_id}</span>}
        </div>
      )}
    </div>
  )
}
