import type { SourceHit } from '../materials/types'

export type SourceAttribution = { source_kind?: 'source_based' | 'supplemental'; source_ids?: string[] }
export type MaterialEvidence = { method: 'none' | 'keyword'; sources: Array<SourceHit & { id: string }> }

export type LearningJobStatus =
  | 'queued'
  | 'planning'
  | 'writing'
  | 'reviewing'
  | 'revising'
  | 'needs_attention'
  | 'ready'
  | 'needs_review'
  | 'failed'
  | 'cancelled'

export type LearningJob = {
  id: number
  course_id: number
  section_id: number
  point_id: number
  outline_version_id: number | null
  status: LearningJobStatus
  revision_count: number
  plan_id: number | null
  content_version_id: number | null
  error: string | null
  created_at: string
  updated_at: string
}

export type ContentExample = SourceAttribution & {
  title: string
  explanation_markdown: string
  code: string | null
  language: string | null
}

export type ContentExercise = SourceAttribution & {
  kind: 'single_choice' | 'multiple_choice' | 'true_false' | 'short_answer'
  question: string
  options: Array<{
    label: string
    text: string
    correct: boolean
  }>
  hint: string | null
  answer: string
  explanation: string
}

export type CodeLab = SourceAttribution & {
  title: string
  instructions_markdown: string
  language: 'python'
  starter_code: string
  solution_code: string
  tests: Array<{
    name: string
    assertion_code: string
  }>
}

export type LearningContent = {
  lesson_markdown: string
  learning_goals: string[]
  lesson_cards: Array<SourceAttribution & { title: string; body_markdown: string }>
  material_evidence?: MaterialEvidence | null
  source_gaps?: string[]
  examples: ContentExample[]
  exercises: ContentExercise[]
  code_lab: CodeLab | null
  summary: string
}

export type ContentReview = {
  approved: boolean
  issues: string[]
  revision_instructions: string[]
}

export type PointContentVersion = {
  id: number
  point_id: number
  outline_version_id: number | null
  version_number: number
  origin: 'generated' | 'legacy'
  content: LearningContent
  review: ContentReview
  created_at: string
}

export const ACTIVE_LEARNING_STATUSES: ReadonlySet<LearningJobStatus> = new Set([
  'queued',
  'planning',
  'writing',
  'reviewing',
  'revising',
])

export function isActiveLearningJob(job: LearningJob | null): boolean {
  return !!job && ACTIVE_LEARNING_STATUSES.has(job.status)
}

export function learningJobStatusText(job: LearningJob | null): string {
  if (!job) return ''
  const labels: Record<LearningJobStatus, string> = {
    queued: '已加入生成队列',
    planning: '正在规划本小节的教学分工',
    writing: '正在撰写讲解与按需学习内容',
    reviewing: '正在审查内容质量',
    revising: `正在根据审查意见修订${job.revision_count ? `（第 ${job.revision_count} 次）` : ''}`,
    needs_attention: '上次调用结果不确定，需要你决定是否重试',
    ready: '学习内容已生成并保存',
    needs_review: '自动审查后仍需人工确认',
    failed: '本次内容生成失败',
    cancelled: '已停止本次内容生成',
  }
  return labels[job.status]
}
