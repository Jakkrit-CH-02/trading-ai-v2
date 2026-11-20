import type { components } from './api-types'

export type Schemas = components['schemas']

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/v1${path}`, { headers: { Accept: 'application/json' }, ...init })
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText}`)
  return (await res.json()) as T
}

/** Decimal strings from the API → number for display. Money math stays on the server. */
export const num = (s: string | number | null | undefined): number => (s == null ? NaN : Number(s))
