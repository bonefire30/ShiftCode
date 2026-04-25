type Props = {
  analyze: Record<string, unknown> | null
}

export function AnalysisSummary({ analyze }: Props) {
  if (!analyze) return null

  return (
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
  )
}
