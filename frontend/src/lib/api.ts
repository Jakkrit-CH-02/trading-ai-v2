import { refresh, useAuth } from './auth'
import type { components } from './api-types'

export type Schemas = components['schemas']

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request(path: string, init: RequestInit | undefined, retry: boolean): Promise<Response> {
  const token = useAuth.getState().token
  const headers = new Headers(init?.headers)
  headers.set('Accept', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const res = await fetch(`/api/v1${path}`, { ...init, headers })
  if (res.status === 401 && retry && !res.headers.has('X-Totp-Required') && (await refresh())) return request(path, init, false)
  return res
}

/** `totp` adds the X-TOTP header that risky endpoints require (SPEC 8). */
export async function api<T>(path: string, init?: RequestInit & { totp?: string }): Promise<T> {
  const { totp, ...rest } = init ?? {}
  const withTotp = totp ? { ...rest, headers: { ...(rest.headers as Record<string, string>), 'X-TOTP': totp } } : rest
  const res = await request(path, withTotp, true)
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail)
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

/** Decimal strings from the API → number for display. Money math stays on the server. */
export const num = (s: string | number | null | undefined): number => (s == null ? NaN : Number(s))
