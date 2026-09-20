import type { CodeLab, ContentExercise, SourceAttribution } from '../learning/types'

export type CardKind = 'lesson' | 'example' | 'exercise' | 'code_lab'
export type LearnerExercise = Omit<ContentExercise, 'answer' | 'explanation' | 'options'> & {
  options: Array<{ label: string; text: string }>
}
export type LearningCard = SourceAttribution & {
  id: string
  kind: CardKind
  title: string
  body_markdown?: string
  code?: string | null
  language?: string | null
  exercise?: LearnerExercise
  lab?: CodeLab
}
export type ExerciseResponse = {
  selected: number[]
  written_answer: string
  correct: boolean | null
  answer: string
  explanation: string
}
export type TutorTurn = {
  id: number
  card_id: string
  action: string
  status: 'queued' | 'running' | 'ready' | 'failed'
  user_message: string | null
  reply_markdown: string | null
  error: string | null
  teacher_action: 'stay' | 'show_next_card' | null
}
export type TutorSession = {
  id: number
  course_id: number
  point_id: number
  outline_version_id: number | null
  content_version_id: number
  revision: number
  card_index: number
  card_count: number
  completed: boolean
  busy: boolean
  current_card: LearningCard
  card_tabs: Array<Pick<LearningCard, 'id' | 'title' | 'kind'>>
  stages: Array<{ kind: CardKind; count: number }>
  response: ExerciseResponse | null
  turns: TutorTurn[]
  timeline: Array<{type:'card';id:string;card:LearningCard;response:ExerciseResponse|null} | {type:'message';id:string;turn:TutorTurn}>
  timeline_truncated: boolean
}
export type TutorAction = {
  request_id: string
  revision: number
  card_id: string
  action: 'next' | 'previous' | 'message' | 'answer' | 'open'
  target_card_id?: string
  message?: string
  selected?: number[]
  written_answer?: string
}
export const stageLabels: Record<CardKind, string> = {
  lesson: '讲解', example: '示例', exercise: '练习', code_lab: '代码实验',
}
