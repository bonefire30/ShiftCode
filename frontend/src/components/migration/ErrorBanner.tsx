type Props = {
  error: string | null
}

export function ErrorBanner({ error }: Props) {
  if (!error) return null

  return (
    <div className="p-3 rounded border border-red-900/50 bg-red-950/40 text-red-200 text-sm">
      {error}
    </div>
  )
}
