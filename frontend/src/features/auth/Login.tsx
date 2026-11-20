import { useState, type FormEvent } from 'react'
import { login } from '../../lib/auth'
import { Card, PrimaryButton } from '../../ui'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [totp, setTotp] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email, password, totp)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'เข้าสู่ระบบไม่สำเร็จ')
      setTotp('')
    } finally {
      setBusy(false)
    }
  }

  const field = 'shadow-inset rounded-control w-full bg-transparent px-4 py-3 outline-none'
  return (
    <main className="grid min-h-screen place-items-center p-6">
      <form onSubmit={submit} className="w-full max-w-sm">
        <Card title="Softtrade" subtitle="เข้าสู่ระบบ (ต้องใช้รหัส 2FA)">
          <label className="flex flex-col gap-1">
            <span className="text-secondary text-[11px]">อีเมล</span>
            <input className={field} type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-secondary text-[11px]">รหัสผ่าน</span>
            <input className={field} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-secondary text-[11px]">รหัส 2FA (6 หลัก)</span>
            <input className={`${field} tracking-[0.4em]`} inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={totp} onChange={(e) => setTotp(e.target.value.replace(/\D/g, ''))} required />
          </label>
          {error && (
            <p role="alert" className="text-down text-[13px]">
              {error}
            </p>
          )}
          <PrimaryButton type="submit" disabled={busy || totp.length !== 6}>
            {busy ? 'กำลังเข้าสู่ระบบ…' : 'Sign in'}
          </PrimaryButton>
        </Card>
      </form>
    </main>
  )
}
