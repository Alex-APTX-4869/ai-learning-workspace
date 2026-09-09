const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        // FormData 必须由浏览器自动设置带 boundary 的 Content-Type。
        ...(options.body && !isFormData ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    })
  } catch {
    throw new Error('暂时无法连接后端，请确认服务已启动后重试。')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const message =
      typeof body?.detail === 'string'
        ? body.detail
        : response.status === 422
          ? '请检查课程名称和学习目标是否填写完整。'
          : `请求未完成（${response.status}），请稍后重试。`
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : '操作未完成，请重试。'
