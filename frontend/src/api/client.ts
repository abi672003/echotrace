const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api/v1'

export interface ApiError {
  code: string
  message: string
}

export class ApiRequestError extends Error {
  code: string

  constructor(error: ApiError) {
    super(error.message)
    this.code = error.code
  }
}

let adminToken: string | null = null

export function setAdminToken(token: string | null): void {
  adminToken = token
}

function buildHeaders(hasBody: boolean): HeadersInit {
  const headers: Record<string, string> = {}
  if (hasBody) {
    headers['Content-Type'] = 'application/json'
  }
  if (adminToken) {
    headers['X-Admin-Token'] = adminToken
  }
  return headers
}

async function handleResponse<T>(response: Response): Promise<T> {
  const text = await response.text()
  const data: unknown = text ? JSON.parse(text) : undefined

  if (!response.ok) {
    const parsed = data as { error?: ApiError } | undefined
    const error: ApiError = parsed?.error ?? {
      code: String(response.status),
      message: response.statusText || 'Request failed',
    }
    throw new ApiRequestError(error)
  }

  return data as T
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'GET',
    headers: buildHeaders(false),
  })
  return handleResponse<T>(response)
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: buildHeaders(body !== undefined),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  return handleResponse<T>(response)
}
