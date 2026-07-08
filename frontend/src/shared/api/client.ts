import type { ApiErrorBody } from './types'

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1'

type UnsafeMethod = 'POST' | 'PUT' | 'PATCH' | 'DELETE'
type ApiMethod = 'GET' | UnsafeMethod

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>

  constructor(status: number, code: string, message: string, details?: Record<string, unknown>) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details || {}
  }
}

let unauthorizedHandler: (() => void) | undefined

export function setUnauthorizedHandler(handler: () => void) {
  unauthorizedHandler = handler
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

export function errorMessage(error: unknown): string {
  if (isApiError(error)) return error.message
  if (error instanceof Error) return error.message
  return 'Не удалось выполнить действие'
}

interface RequestOptions<TBody> {
  method?: ApiMethod
  body?: TBody
  signal?: AbortSignal
}

const unsafeMethods = new Set<ApiMethod>(['POST', 'PUT', 'PATCH', 'DELETE'])

export async function apiFetch<TResponse, TBody = unknown>(
  path: string,
  options: RequestOptions<TBody> = {},
): Promise<TResponse> {
  const method = options.method || 'GET'
  const headers = new Headers()
  const hasBody = options.body !== undefined

  if (hasBody) headers.set('Content-Type', 'application/json')
  if (unsafeMethods.has(method)) headers.set('X-Requested-With', 'XMLHttpRequest')

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    credentials: 'include',
    headers,
    body: hasBody ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  })

  const data = await readBody(response)

  if (!response.ok) {
    const body = data as ApiErrorBody | undefined
    const apiError = body?.error
    const message = apiError?.message || fallbackMessage(response.status)
    const code = apiError?.code || `http_${response.status}`
    const details = apiError?.details || {}
    const error = new ApiError(response.status, code, message, details)

    if (response.status === 401) unauthorizedHandler?.()
    throw error
  }

  return data as TResponse
}

async function readBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type') || ''
  if (response.status === 204) return undefined
  if (contentType.includes('application/json')) return response.json()
  const text = await response.text()
  return text ? { message: text } : undefined
}

function fallbackMessage(status: number): string {
  if (status === 401) return 'Сессия истекла — войдите заново'
  if (status === 403) return 'Недостаточно прав для действия'
  if (status === 404) return 'Запись не найдена'
  if (status === 422) return 'Проверьте заполнение формы'
  if (status >= 500) return 'Сервер временно недоступен'
  return 'Запрос не выполнен'
}
