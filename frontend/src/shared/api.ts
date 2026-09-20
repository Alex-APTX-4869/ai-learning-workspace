const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export const apiUrl = (path: string) => `${API_BASE}${path}`

export class HttpError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'HttpError'
    this.status = status
  }
}

export async function httpErrorFromResponse(response: Response) {
  const body = await response.json().catch(() => null)
  const detail = body?.detail
  let message: string | null = typeof detail === 'string' ? detail : null
  if (Array.isArray(detail)) {
    const validation = detail.find(
      (item: unknown) =>
        typeof item === 'object' && item !== null && typeof (item as { msg?: unknown }).msg === 'string',
    ) as { msg: string } | undefined
    if (validation) message = `输入内容有误：${validation.msg}`
  }
  return new HttpError(
    message ||
      (response.status === 422
        ? '输入内容有误，请检查后重试。'
        : `请求未完成（${response.status}），请稍后重试。`),
    response.status,
  )
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData
    response = await fetch(apiUrl(path), {
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
    throw await httpErrorFromResponse(response)
  }
  return response.json() as Promise<T>
}

export const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : '操作未完成，请重试。'
