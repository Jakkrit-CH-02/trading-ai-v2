import { create } from 'zustand'
import { ConfirmDialog } from '../ui'

type Pending = { title: string; description?: string; resolve: (code: string | null) => void }
const useTotpStore = create<{ pending: Pending | null }>(() => ({ pending: null }))

/** Opens the TOTP dialog and resolves with the 6-digit code, or null when cancelled.
 *  Risky actions (SPEC 8) call this before sending the X-TOTP header. */
export function askTotp(title: string, description?: string): Promise<string | null> {
  return new Promise((resolve) => useTotpStore.setState({ pending: { title, description, resolve } }))
}

export function TotpHost() {
  const pending = useTotpStore((s) => s.pending)
  if (!pending) return null
  const close = (code: string | null) => {
    pending.resolve(code)
    useTotpStore.setState({ pending: null })
  }
  return (
    <ConfirmDialog
      open
      title={pending.title}
      description={pending.description}
      requireTotp
      confirmLabel="Confirm"
      onOpenChange={(o) => !o && close(null)}
      onConfirm={(code) => close(code ?? null)}
    />
  )
}
