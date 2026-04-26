import type { CaseItem, LlmEvaluationProfile } from './types'

const LLM_EVALUATION_PROFILES: Array<{
  value: LlmEvaluationProfile
  label: string
  description: string
}> = [
  { value: 'minimax', label: 'minimax', description: 'MiniMax-M2.7 · low-cost candidate' },
  { value: 'deepseek', label: 'deepseek', description: 'deepseek-v4-flash · code-focused candidate' },
  {
    value: 'codex-proxy',
    label: 'codex-proxy',
    description: 'GPT-5.3 Codex · high-quality baseline',
  },
]

type Props = {
  cases: CaseItem[]
  projectPath: string
  setProjectPath: (value: string) => void
  maxRepair: number
  setMaxRepair: (value: number) => void
  goModule: string
  setGoModule: (value: string) => void
  llmProfile: LlmEvaluationProfile
  setLlmProfile: (value: LlmEvaluationProfile) => void
  running: boolean
  analyzing: boolean
  onAnalyze: () => void
  onStart: () => void
  onStop: () => void
}

export function MigrationSetupPanel({
  cases,
  projectPath,
  setProjectPath,
  maxRepair,
  setMaxRepair,
  goModule,
  setGoModule,
  llmProfile,
  setLlmProfile,
  running,
  analyzing,
  onAnalyze,
  onStart,
  onStop,
}: Props) {
  return (
    <div className="flex flex-wrap gap-3 items-end">
      <div className="flex flex-col gap-1 text-sm min-w-[320px]">
        <span className="text-slate-400">项目目录 (benchmark 用例，与单文件页一致)</span>
        {cases.length > 0 ? (
          <select
            className="bg-slate-900 border border-slate-700 rounded px-3 py-2 min-w-[280px] w-full"
            value={cases.some((c) => c.path === projectPath) ? projectPath : '__manual__'}
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
      <label className="flex flex-col gap-1 text-sm min-w-[260px]">
        <span className="text-slate-400">LLM profile for evaluation</span>
        <select
          className="bg-slate-900 border border-slate-700 rounded px-3 py-2"
          value={llmProfile}
          onChange={(e) => setLlmProfile(e.target.value as LlmEvaluationProfile)}
          disabled={running}
        >
          {LLM_EVALUATION_PROFILES.map((profile) => (
            <option key={profile.value} value={profile.value}>
              {profile.label} — {profile.description}
            </option>
          ))}
        </select>
        <span className="text-xs text-slate-500">
          仅用于本次转换评估；不显示 API key，也不代表模型已被完全支持。
        </span>
      </label>
      <button
        type="button"
        onClick={onAnalyze}
        disabled={analyzing || !projectPath}
        className="px-4 py-2 rounded bg-slate-700 hover:bg-slate-600 text-sm"
      >
        {analyzing ? '分析中…' : '仅扫描/依赖图'}
      </button>
      <button
        type="button"
        onClick={onStart}
        disabled={running}
        className="px-4 py-2 rounded bg-violet-600 hover:bg-violet-500 text-sm text-white font-medium"
      >
        开始项目迁移
      </button>
      <button
        type="button"
        onClick={onStop}
        disabled={!running}
        className="px-4 py-2 rounded bg-slate-700 text-sm"
      >
        停止
      </button>
    </div>
  )
}
