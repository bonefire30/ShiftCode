export type CaseItem = { id: string; name: string; path: string }

export type LlmEvaluationProfile = 'minimax' | 'deepseek' | 'codex-proxy'

export type LlmCallStatus = 'success' | 'warning' | 'error' | 'unknown'

export type LlmEvaluationMetadata = {
  profile?: string | null
  provider?: string | null
  model?: string | null
  baseUrl?: string | null
  latencyMs?: number | null
  promptTokens?: number | null
  completionTokens?: number | null
  totalTokens?: number | null
  llmCallStatus?: LlmCallStatus | string | null
  conversionStatus?: string | null
  errorMessage?: string | null
  retryable?: boolean | null
}

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
