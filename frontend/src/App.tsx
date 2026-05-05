import { ProjectMigration } from './ProjectMigration'

function App() {
  return (
    <div className="min-h-screen flex flex-col p-4 max-w-[1920px] mx-auto">
      <header className="border-b border-slate-800 pb-4 mb-4">
        <h1 className="text-xl font-semibold text-white tracking-tight">
          ShiftCode
          <span className="text-slate-500 font-normal ml-2">
            Project Migration
          </span>
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Project-level Java to Go migration with dependency analysis, module
          translation, generated tests, and build/test repair loops.
        </p>
      </header>

      <section className="mb-4 rounded-lg border border-slate-800 bg-slate-900/20 p-4 text-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-medium text-slate-200">External trial quick start</h2>
            <p className="mt-1 text-xs text-slate-500">
              面向第一次试用的用户。先看整体状态，再看原因和 next actions，不要把 build success 当作完整语义成功。
            </p>
          </div>
          <span className="rounded-full border border-slate-700 px-2 py-1 text-[11px] text-slate-400">
            Low-cost path first
          </span>
        </div>

        <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-3">
          <div className="rounded border border-slate-800 bg-slate-950/40 p-3">
            <p className="font-medium text-slate-200">1. Pick a small trial input</p>
            <p className="mt-1 text-xs text-slate-500">
              优先选择 benchmark 列表里体量小、名字清晰的项目。先看成功或 mostly-supported 路径，再看 partial 示例。
            </p>
          </div>
          <div className="rounded border border-slate-800 bg-slate-950/40 p-3">
            <p className="font-medium text-slate-200">2. Start with low-cost validation</p>
            <p className="mt-1 text-xs text-slate-500">
              默认先用本地 mock/默认验证路径理解报告结构。不要在第一次试用时直接假设需要真实 LLM API key。
            </p>
          </div>
          <div className="rounded border border-slate-800 bg-slate-950/40 p-3">
            <p className="font-medium text-slate-200">3. Read results in order</p>
            <p className="mt-1 text-xs text-slate-500">
              先看 conversion status，再看 status reasons、test issues、recommended next actions，最后再决定是否值得继续深入试用。
            </p>
          </div>
        </div>
      </section>

      <div className="border border-slate-800 rounded-lg p-4 bg-slate-900/20">
        <ProjectMigration />
      </div>
    </div>
  )
}

export default App
