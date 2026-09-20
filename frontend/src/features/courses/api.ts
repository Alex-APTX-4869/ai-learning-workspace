import { request } from '../../shared/api'
import type { Course, CourseInput, CourseSummary } from './types'
import type { CourseBrief } from './briefTypes'

export const coursesApi = {
  list: () => request<CourseSummary[]>('/courses'),
  get: (id: number) => request<Course>(`/courses/${id}`),
  version: (id: number, versionId: number) =>
    request<Course>(`/courses/${id}/outline-versions/${versionId}/course`),
  brief: (id: number, outlineId: number | null) =>
    request<CourseBrief | null>(`/courses/${id}/brief${outlineId ? `?outline_version_id=${outlineId}` : ''}`),
  create: (input: CourseInput) =>
    request<Course>('/courses', { method: 'POST', body: JSON.stringify(input) }),
  update: (id: number, input: CourseInput) =>
    request<Course>(`/courses/${id}`, { method: 'PATCH', body: JSON.stringify(input) }),
  outline: (id: number) => request<Course>(`/courses/${id}/outline`, { method: 'POST' }),
  points: (courseId: number, chapterId: number, outlineId: number | null) =>
    request<Course>(`/courses/${courseId}/chapters/${chapterId}/points${outlineId ? `?outline_version_id=${outlineId}` : ''}`, { method: 'POST' }),
}
