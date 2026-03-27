const RAW_API_BASE = (import.meta as any).env?.VITE_API_BASE || '/api'
const API_BASE = String(RAW_API_BASE).replace(/\/+$/, '')
const RAW_API_TOKEN = (import.meta as any).env?.VITE_API_TOKEN || ''
const API_TOKEN = String(RAW_API_TOKEN).trim()

function buildHeaders(extraHeaders?: Record<string, string>, contentType?: string): Record<string, string> {
  const headers: Record<string, string> = { ...(extraHeaders || {}) }

  const hasAuthHeader = Object.keys(headers).some((key) => {
    const lower = key.toLowerCase()
    return lower === 'authorization' || lower === 'x-api-token'
  })

  if (API_TOKEN && !hasAuthHeader) {
    headers.Authorization = `Bearer ${API_TOKEN}`
  }

  const hasContentType = Object.keys(headers).some((key) => key.toLowerCase() === 'content-type')
  if (contentType && !hasContentType) {
    headers['Content-Type'] = contentType
  }

  return headers
}

async function requestJson<T>(
  path: string,
  init: RequestInit,
): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, init)
  if (!r.ok) {
    const text = await r.text()
    let msg = (text || '').trim()
    try {
      const obj = JSON.parse(text)
      if (obj && typeof obj === 'object') {
        const anyObj = obj as any
        const detail = anyObj?.detail
        const message = anyObj?.message
        if (typeof detail === 'string' && detail.trim()) {
          msg = detail.trim()
        } else if (typeof message === 'string' && message.trim()) {
          msg = message.trim()
        }
      }
    } catch {
    }
    if (!msg) {
      msg = `HTTP ${r.status}`
    }
    msg = msg.replace(/^\s*\d{3}:\s*/g, '')
    throw new Error(msg)
  }
  return (await r.json()) as T
}

export async function apiGet<T>(path: string, extraHeaders?: Record<string, string>): Promise<T> {
  return await requestJson<T>(
    path,
    {
      headers: buildHeaders(extraHeaders),
    },
  )
}

export async function apiPost<T>(path: string, body: any, extraHeaders?: Record<string, string>): Promise<T> {
  return await requestJson<T>(
    path,
    {
      method: 'POST',
      headers: buildHeaders(extraHeaders, 'application/json'),
      body: JSON.stringify(body),
    },
  )
}

export async function apiPut<T>(path: string, body: any, extraHeaders?: Record<string, string>): Promise<T> {
  return await requestJson<T>(
    path,
    {
      method: 'PUT',
      headers: buildHeaders(extraHeaders, 'application/json'),
      body: JSON.stringify(body),
    },
  )
}

export async function apiDelete<T>(path: string, extraHeaders?: Record<string, string>): Promise<T> {
  return await requestJson<T>(
    path,
    {
      method: 'DELETE',
      headers: buildHeaders(extraHeaders),
    },
  )
}
