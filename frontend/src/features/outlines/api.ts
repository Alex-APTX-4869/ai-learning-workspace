import { apiUrl, httpErrorFromResponse, request } from '../../shared/api'
import type { OutlineActivation, OutlineGenerationInput, OutlineStreamEvent, OutlineVersion } from './types'

function parseEvent(line: string): OutlineStreamEvent | null {
  const value = line.trim()
  if (!value || value.startsWith(':') || value.startsWith('event:')) return null
  const json = value.startsWith('data:') ? value.slice(5).trim() : value
  if (!json || json === '[DONE]') return null
  return JSON.parse(json) as OutlineStreamEvent
}

export const outlineVersionsApi = {
  list: (courseId: number) =>
    request<OutlineVersion[]>(`/courses/${courseId}/outline-versions`),
  selected: (courseId: number) =>
    request<OutlineVersion>(`/courses/${courseId}/outline-versions/selected`),
  select: (courseId: number, versionId: number) =>
    request<OutlineVersion>(`/courses/${courseId}/outline-versions/${versionId}/select`, {
      method: 'POST',
    }),
  activate: (courseId: number, versionId: number) =>
    request<OutlineActivation>(`/courses/${courseId}/outline-versions/${versionId}/activate`, {
      method: 'POST',
    }),
  course: (courseId: number, versionId: number) =>
    request<import('../courses/types').Course>(
      `/courses/${courseId}/outline-versions/${versionId}/course`,
    ),
  async stream(
    courseId: number,
    input: OutlineGenerationInput,
    onEvent: (event: OutlineStreamEvent) => void,
    signal?: AbortSignal,
  ) {
    let response: Response
    try {
      response = await fetch(apiUrl(`/courses/${courseId}/outline-versions/stream`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/x-ndjson, text/event-stream',
        },
        body: JSON.stringify(input),
        signal,
      })
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
      throw new Error('暂时无法连接后端，请确认服务已启动后重试。')
    }
    if (!response.ok) throw await httpErrorFromResponse(response)
    if (!response.body) throw new Error('浏览器没有收到可读取的流式响应。')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    try {
      while (true) {
        const { done, value } = await reader.read()
        buffer += decoder.decode(value, { stream: !done })
        const lines = buffer.split(/\r?\n/)
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          const event = parseEvent(line)
          if (event) onEvent(event)
        }
        if (done) break
      }
      const finalEvent = parseEvent(buffer)
      if (finalEvent) onEvent(finalEvent)
    } finally {
      reader.releaseLock()
    }
  },
}
