import { request } from '../../shared/api'
import type { CourseBrief, IntakeConfirmation, IntakeRead, OptionExplanation } from './types'

export const intakeApi = {
  create: (name: string, intro: string, materialBatchId?: string | null) =>
    request<IntakeRead>('/course-intakes', {
      method: 'POST',
      body: JSON.stringify({ name, intro, material_batch_id: materialBatchId || null }),
    }),
  get: (id: number) => request<IntakeRead>(`/course-intakes/${id}`),
  resume: (id: number) => request<IntakeRead>(`/course-intakes/${id}/resume`, {method:'POST'}),
  latestActive: () => request<IntakeRead>('/course-intakes/latest-active'),
  selectDepth: (id: number, choice: { option_id: string } | { question_count: number }) =>
    request<IntakeRead>(`/course-intakes/${id}/depth`, {
      method: 'POST',
      body: JSON.stringify(choice),
    }),
  answer: (
    id: number,
    answer:
      | { question_id: string; option_id: string }
      | { question_id: string; custom_answer: string },
  ) =>
    request<IntakeRead>(`/course-intakes/${id}/answers`, {
      method: 'POST',
      body: JSON.stringify(answer),
    }),
  explainOption: (id: number, questionId: string, optionId: string) =>
    request<OptionExplanation>(
      `/course-intakes/${id}/questions/${encodeURIComponent(questionId)}/options/${encodeURIComponent(optionId)}/explain`,
      { method: 'POST' },
    ),
  confirm: (id: number, brief: CourseBrief) =>
    request<IntakeConfirmation>(`/course-intakes/${id}/confirm`, {
      method: 'POST',
      body: JSON.stringify({ brief }),
    }),
}
