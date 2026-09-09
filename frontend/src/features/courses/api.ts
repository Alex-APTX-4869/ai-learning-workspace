import { request } from '../../shared/api'
import type { Course, CourseInput, CourseSummary } from './types'

export const coursesApi = {
  list: () => request<CourseSummary[]>('/courses'),
  get: (id: number) => request<Course>(`/courses/${id}`),
  create: (input: CourseInput) =>
    request<Course>('/courses', { method: 'POST', body: JSON.stringify(input) }),
  update: (id: number, input: CourseInput) =>
    request<Course>(`/courses/${id}`, { method: 'PATCH', body: JSON.stringify(input) }),
  outline: (id: number) => request<Course>(`/courses/${id}/outline`, { method: 'POST' }),
  points: (courseId: number, chapterId: number) =>
    request<Course>(`/courses/${courseId}/chapters/${chapterId}/points`, { method: 'POST' }),
}
