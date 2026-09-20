import { request } from '../../shared/api'
import type { LearningJob, PointContentVersion } from './types'

export const learningApi = {
  content: (courseId: number, outlineId: number | null, pointId: number, signal?: AbortSignal) =>
    request<PointContentVersion>(`/courses/${courseId}/points/${pointId}/content${outlineId ? `?outline_version_id=${outlineId}` : ''}`, { signal }),
  startContentJob: (courseId: number, outlineId: number | null, pointId: number, signal?: AbortSignal) =>
    request<LearningJob>(`/courses/${courseId}/points/${pointId}/content/jobs${outlineId ? `?outline_version_id=${outlineId}` : ''}`, {
      method: 'POST',
      signal,
    }),
  activeJob: (courseId: number, outlineId: number | null, pointId: number, signal?: AbortSignal) =>
    request<LearningJob | null>(
      `/courses/${courseId}/points/${pointId}/content/jobs/active${outlineId ? `?outline_version_id=${outlineId}` : ''}`,
      { signal },
    ),
  job: (jobId: number, signal?: AbortSignal) =>
    request<LearningJob>(`/learning-jobs/${jobId}`, { signal }),
  cancelJob: (jobId: number, signal?: AbortSignal) =>
    request<LearningJob>(`/learning-jobs/${jobId}/cancel`, {
      method: 'POST',
      signal,
    }),
  retryJob: (jobId: number, signal?: AbortSignal) =>
    request<LearningJob>(`/learning-jobs/${jobId}/retry`, { method: 'POST', signal }),
}
