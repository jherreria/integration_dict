// Fetch wrapper: JSON handling, typed errors, abort support, and detection
// of the Databricks Apps OAuth proxy session expiring (302 -> HTML login).

export const API_BASE = '/api'

export class ApiError extends Error {
  status: number
  detail: string
  fields?: string[]

  constructor(status: number, detail: string, fields?: string[]) {
    super(detail)
    this.status = status
    this.detail = detail
    this.fields = fields
  }
}

export class SessionExpiredError extends Error {
  constructor() {
    super('Your session has expired. Please reload the page to sign in again.')
  }
}

function extractDetail(body: unknown): { detail: string; fields?: string[] } {
  if (body && typeof body === 'object') {
    const d = (body as Record<string, unknown>).detail
    if (typeof d === 'string') return { detail: d }
    if (d && typeof d === 'object') {
      const obj = d as Record<string, unknown>
      return {
        detail: typeof obj.detail === 'string' ? obj.detail : JSON.stringify(d),
        fields: Array.isArray(obj.fields) ? (obj.fields as string[]) : undefined,
      }
    }
    if (Array.isArray(d)) {
      // FastAPI validation errors
      const first = d[0] as { msg?: string; loc?: unknown[] } | undefined
      if (first?.msg) {
        const loc = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : ''
        return { detail: `${String(loc)}: ${first.msg}` }
      }
    }
  }
  return { detail: 'Request failed' }
}

export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      // Only set a JSON content type for string bodies; let the browser set
      // the multipart boundary itself for FormData uploads.
      headers: {
        Accept: 'application/json',
        ...(typeof options.body === 'string' ? { 'Content-Type': 'application/json' } : {}),
      },
      ...options,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError(0, 'Network error — please check your connection and try again.')
  }

  // The Databricks Apps auth proxy answers an expired session with a
  // redirect to an HTML login page rather than JSON.
  const contentType = response.headers.get('content-type') ?? ''
  if (response.redirected && !contentType.includes('application/json')) {
    throw new SessionExpiredError()
  }

  if (response.status === 204) return undefined as T

  if (!contentType.includes('application/json')) {
    if (response.ok) throw new SessionExpiredError()
    throw new ApiError(response.status, `Unexpected response (${response.status})`)
  }

  const body = await response.json()
  if (!response.ok) {
    const { detail, fields } = extractDetail(body)
    throw new ApiError(response.status, detail, fields)
  }
  return body as T
}

export const get = <T>(path: string, signal?: AbortSignal) =>
  request<T>(path, { signal })

export const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const postForm = <T>(path: string, form: FormData) =>
  request<T>(path, { method: 'POST', body: form })

export const patch = <T>(path: string, body: unknown) =>
  request<T>(path, { method: 'PATCH', body: JSON.stringify(body) })

export const del = <T>(path: string) => request<T>(path, { method: 'DELETE' })
