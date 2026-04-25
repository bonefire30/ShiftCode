export type WorkflowStageId =
  | 'architect'
  | 'hitl_gateway'
  | 'translate_modules'
  | 'merge_all'
  | 'test_gen_modules'
  | 'reviewer'
  | 'global_repair'
  | 'test_gen_repair'

export type WorkflowStage = {
  id: WorkflowStageId
  label: string
  description: string
}

export const WORKFLOW_STAGES: WorkflowStage[] = [
  {
    id: 'architect',
    label: '分析项目结构',
    description: '扫描 Java 文件、解析依赖图、规划翻译批次。',
  },
  {
    id: 'hitl_gateway',
    label: '确认框架策略',
    description: '识别 Spring/JPA/JAX-RS 等框架特征，需要时等待人工决策。',
  },
  {
    id: 'translate_modules',
    label: '翻译模块',
    description: '按依赖顺序把 Java 模块翻译成 Go 代码。',
  },
  {
    id: 'merge_all',
    label: '整理迁移产物',
    description: '汇总已写入的 Go 文件，准备生成测试和构建检查。',
  },
  {
    id: 'test_gen_modules',
    label: '生成测试',
    description: '为迁移后的 Go 模块生成 *_test.go。',
  },
  {
    id: 'reviewer',
    label: '构建与测试',
    description: '运行 go build ./... 和 go test ./... 验证产物。',
  },
  {
    id: 'global_repair',
    label: '修复构建问题',
    description: '根据 build/test 输出修复 Go 代码。',
  },
  {
    id: 'test_gen_repair',
    label: '修复测试问题',
    description: '修复测试生成不足、过度指定或测试失败。',
  },
]

export function getWorkflowStage(node: string | null | undefined) {
  if (!node) return null
  return WORKFLOW_STAGES.find((stage) => stage.id === node) ?? null
}
