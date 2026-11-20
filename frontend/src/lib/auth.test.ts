import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from './api'
import { login, refresh, useAuth } from './auth'

const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers })

afterEach(() => {
  vi.unstubAllGlobals()
  useAuth.getState().set(null, null)
})

describe('auth', () => {
  it('keeps the access token in memory only', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ access_token: 'tok', email: 'a@b.c' })))
    await login('a@b.c', 'pw', '123456')
    expect(useAuth.getState().token).toBe('tok')
    expect(JSON.stringify({ ...localStorage })).not.toContain('tok')
  })

  it('shows a generic message on bad credentials and the wait time on lockout', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ detail: 'invalid credentials' }, 401)))
    await expect(login('a', 'b', 'c')).rejects.toThrow('ไม่ถูกต้อง')
    vi.stubGlobal('fetch', vi.fn(async () => json({}, 429, { 'Retry-After': '600' })))
    await expect(login('a', 'b', 'c')).rejects.toThrow('600')
  })

  it('on 401 refreshes once from the cookie and retries the request with the new token', async () => {
    useAuth.getState().set('old', 'a@b.c')
    const calls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        const auth = new Headers(init?.headers).get('Authorization')
        calls.push(`${url} ${auth}`)
        if (url.endsWith('/auth/refresh')) return json({ access_token: 'new', email: 'a@b.c' })
        return auth === 'Bearer new' ? json({ ok: true }) : json({ detail: 'expired' }, 401)
      }),
    )
    await expect(api('/bots')).resolves.toEqual({ ok: true })
    expect(calls).toEqual(['/api/v1/bots Bearer old', '/api/v1/auth/refresh null', '/api/v1/bots Bearer new'])
  })

  it('does not refresh when the server asks for a TOTP code, and surfaces the detail', async () => {
    useAuth.getState().set('t', 'a@b.c')
    const f = vi.fn(async () => json({ detail: 'invalid TOTP code' }, 401, { 'X-Totp-Required': '1' }))
    vi.stubGlobal('fetch', f)
    await expect(api('/risk/profile', { method: 'PUT', totp: '000000' })).rejects.toMatchObject({ status: 401, message: 'invalid TOTP code' })
    expect(f).toHaveBeenCalledTimes(1)
  })

  it('signs the user out when the refresh cookie is gone', async () => {
    useAuth.getState().set('old', 'a@b.c')
    vi.stubGlobal('fetch', vi.fn(async () => json({}, 401)))
    expect(await refresh()).toBe(false)
    expect(useAuth.getState().token).toBeNull()
    await expect(api('/x')).rejects.toBeInstanceOf(ApiError)
  })
})
