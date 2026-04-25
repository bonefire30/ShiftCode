type Props = {
  goOutputDir: unknown
}

export function OutputPathNotice({ goOutputDir }: Props) {
  if (typeof goOutputDir !== 'string' || !goOutputDir) return null

  return <p className="text-xs text-slate-500">Go 输出: {goOutputDir}</p>
}
