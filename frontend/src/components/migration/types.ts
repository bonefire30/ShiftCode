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
  statusReasons?: string[]
  gateFailures?: string[]
  statusCounts?: Record<string, number>
  engineeringStatus?: {
    build?: string | null
    tests?: string | null
    testGeneration?: string | null
    testQuality?: string | null
  }
  projectStatusSummary?: Record<string, number>
  summaryCompleteness?: 'complete' | 'aggregate-only' | 'incomplete' | string | null
  testFailureReasons?: string[]
  testGenerationReasons?: string[]
  recommendedNextActions?: string[]
  conversionItems?: ConversionItem[]
  errorMessage?: string | null
  retryable?: boolean | null
}

export type ConversionItem = {
  id?: string | null
  path?: string | null
  status?: string | null
  semanticStatus?: string | null
  classifierStatus?: string | null
  reasons?: string[]
  testIssueReasons?: string[]
  testGenerationIssueReasons?: string[]
  engineeringStatus?: {
    build?: string | null
    tests?: string | null
    testGeneration?: string | null
    testQuality?: string | null
  }
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
