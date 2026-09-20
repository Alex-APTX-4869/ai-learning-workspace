import type { Course } from '../courses/types'
import type { CourseBrief } from '../courses/briefTypes'

export type { CourseBrief } from '../courses/briefTypes'

export type IntakePhase = 'start' | 'depth' | 'question' | 'brief' | 'extension'

export type DepthOption = {
  id: string
  title: string
  description: string
  question_count: number
  recommended: boolean
}

export type QuestionOption = {
  id: string
  title: string
  description: string
  recommended?: boolean
}

export type InterviewQuestion = {
  extension_reason?: string | null
  id: string
  number: number
  focus_key: string
  baseline?: string
  text: string
  purpose: string
  recommendation_reason?: string | null
  options: QuestionOption[]
}

export type OptionExplanation = {
  plain_explanation: string
  suitable_when: string
  course_impact: string
  example: string
}

export type IntakeAnswer = {
  question_id: string
  focus_key: string
  question_text: string
  baseline?: string
  answer_type: 'option' | 'custom'
  option_id: string | null
  answer: string
  option_description: string | null
}

export type IntakeRead = {
  id: number
  initial_name: string
  initial_intro: string
  status: 'choosing_depth' | 'interviewing' | 'awaiting_extension' | 'ready_to_confirm' | 'completed'
  extension_proposal: {id: string; reason: string; uncertainty: string; question: {text: string}} | null
  depth_options: DepthOption[]
  selected_depth: DepthOption | null
  question_count: number | null
  answers: IntakeAnswer[]
  current_question: InterviewQuestion | null
  brief: CourseBrief | null
  course_id: number | null
  version: number
}

export type IntakeConfirmation = {
  intake: IntakeRead
  course: Course
}
