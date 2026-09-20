import { request } from '../../shared/api'
import type { TutorAction, TutorSession } from './types'

export const tutorApi = {
  start: (courseId: number, outlineId: number | null, pointId: number, contentId: number, signal?: AbortSignal) => {
    const query = new URLSearchParams({ content_version_id: String(contentId) })
    if (outlineId !== null) query.set('outline_version_id', String(outlineId))
    return request<TutorSession>(`/courses/${courseId}/points/${pointId}/tutor-session?${query}`, { method: 'POST', signal })
  },
  session: (sessionId: number, signal?: AbortSignal) =>
    request<TutorSession>(`/tutor-sessions/${sessionId}`, { signal }),
  action: (sessionId: number, action: TutorAction, signal?: AbortSignal) =>
    request<TutorSession>(`/tutor-sessions/${sessionId}/actions`, {
      method: 'POST', body: JSON.stringify(action), signal,
    }),
}
