import { create } from 'zustand'

type AuthState = {
  token: string | null
  email: string | null
  /** true once the first silent refresh (cookie) attempt finished, so the UI can stop showing a spinner */
  ready: boolean
  set: (token: string | null, email: string | null) => void
  setReady: () => void
}

/** The access token lives only in memory (never localStorage): a reload re-creates it from the
 *  httpOnly refresh cookie. */
export const useAuth = create<AuthState>((set) => ({
  token: null,
  email: null,
  ready: false,
  set: (token, email) => set({ token, email }),
  setReady: () => set({ ready: true }),
}))

type TokenOut = { access_token: string; email: string }

export async function login(email: string, password: string, totp: string): Promise<void> {
  const res = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, totp }),
  })
  if (res.status === 429) throw new Error(`ลองผิดบ่อยเกินไป รอ ${res.headers.get('Retry-After') ?? '…'} วินาที`)
  if (!res.ok) throw new Error('อีเมล รหัสผ่าน หรือรหัส 2FA ไม่ถูกต้อง')
  const j = (await res.json()) as TokenOut
  useAuth.getState().set(j.access_token, j.email)
}

let refreshing: Promise<boolean> | null = null

/** Silent refresh from the httpOnly cookie; concurrent callers share one request. */
export function refresh(): Promise<boolean> {
  refreshing ??= (async () => {
    try {
      const res = await fetch('/api/v1/auth/refresh', { method: 'POST' })
      if (!res.ok) throw new Error('no session')
      const j = (await res.json()) as TokenOut
      useAuth.getState().set(j.access_token, j.email)
      return true
    } catch {
      useAuth.getState().set(null, null)
      return false
    } finally {
      refreshing = null
    }
  })()
  return refreshing
}

export async function logout(): Promise<void> {
  await fetch('/api/v1/auth/logout', { method: 'POST' }).catch(() => undefined)
  useAuth.getState().set(null, null)
}
