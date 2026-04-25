export type CaseItem = { id: string; name: string; path: string }

export type FileState = {
  status?: string
  go_code?: string
  last_error_hint?: string
  errors?: string[]
}

export type StepRow = { node: string; at: string; timestamp: number }

export type HitlPayload = {
  thread_id?: string
  question?: string
  key?: string
  type?: string
}
