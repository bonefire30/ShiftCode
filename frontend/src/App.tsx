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

      <div className="border border-slate-800 rounded-lg p-4 bg-slate-900/20">
        <ProjectMigration />
      </div>
    </div>
  )
}

export default App
