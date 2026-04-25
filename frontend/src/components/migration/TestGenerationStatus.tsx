type Props = {
  testGenExpected: number | null
  testGenGenerated: number | null
  testGenOk: boolean | null
  testGenFailures: string[]
  testGenWarnings: string[]
  testQualityOk: boolean | null
}

export function TestGenerationStatus({
  testGenExpected,
  testGenGenerated,
  testGenOk,
  testGenFailures,
  testGenWarnings,
  testQualityOk,
}: Props) {
  const hasStatus =
    testGenExpected !== null ||
    testGenGenerated !== null ||
    testGenFailures.length > 0 ||
    testGenWarnings.length > 0

  if (!hasStatus) return null

  return (
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
  )
}
