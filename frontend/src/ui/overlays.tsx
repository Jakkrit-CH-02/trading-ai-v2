import * as Dialog from '@radix-ui/react-dialog'
import { create } from 'zustand'
import { useState, type ReactNode } from 'react'
import { PrimaryButton } from './controls'
import { cx } from './cx'

type ToastItem = { id: number; kind: 'info' | 'error' | 'risk'; text: string }
let nextId = 1
export const useToasts = create<{ items: ToastItem[]; push: (kind: ToastItem['kind'], text: string) => void; dismiss: (id: number) => void }>((set) => ({
  items: [],
  push: (kind, text) => {
    const id = nextId++
    set((s) => ({ items: [...s.items, { id, kind, text }] }))
    setTimeout(() => set((s) => ({ items: s.items.filter((i) => i.id !== id) })), 6000)
  },
  dismiss: (id) => set((s) => ({ items: s.items.filter((i) => i.id !== id) })),
}))

export function Toaster() {
  const { items, dismiss } = useToasts()
  return (
    <div aria-live="polite" className="fixed right-6 bottom-6 z-50 flex flex-col gap-3">
      {items.map((t) => (
        <div key={t.id} role="status" className={cx('bg-surface shadow-raised-lg rounded-panel flex max-w-sm items-center gap-3 px-4 py-3', t.kind !== 'info' && 'text-down')}>
          <span className="flex-1">{t.text}</span>
          <button aria-label="Dismiss" onClick={() => dismiss(t.id)} className="text-secondary">
            ×
          </button>
        </div>
      ))}
    </div>
  )
}

/** Confirmation for risky actions; `requireTotp` adds the 6-digit second-factor field (SPEC 8). */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  requireTotp,
  confirmLabel = 'Confirm',
  onConfirm,
  children,
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
  title: string
  description?: string
  requireTotp?: boolean
  confirmLabel?: string
  onConfirm: (totp?: string) => void
  children?: ReactNode
}) {
  const [code, setCode] = useState('')
  const valid = !requireTotp || /^\d{6}$/.test(code)
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/30" />
        <Dialog.Content className="bg-surface shadow-raised-lg rounded-card fixed top-1/2 left-1/2 z-50 flex w-[min(92vw,420px)] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 p-6">
          <Dialog.Title className="text-[15px] font-semibold">{title}</Dialog.Title>
          <Dialog.Description className="text-secondary text-[13px]">{description}</Dialog.Description>
          {children}
          {requireTotp && (
            <label className="flex flex-col gap-1">
              <span className="text-secondary text-[11px]">TOTP (6 หลัก)</span>
              <input
                inputMode="numeric"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                className="shadow-inset rounded-control bg-transparent px-4 py-3 tracking-[0.4em] outline-none"
              />
            </label>
          )}
          <div className="flex justify-end gap-3">
            <Dialog.Close className="bg-surface shadow-raised-sm rounded-control px-4 py-2">Cancel</Dialog.Close>
            <PrimaryButton
              disabled={!valid}
              onClick={() => {
                onConfirm(requireTotp ? code : undefined)
                setCode('')
                onOpenChange(false)
              }}
            >
              {confirmLabel}
            </PrimaryButton>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

/** Right-hand drawer for secondary detail (SPEC 10.2). */
export function Drawer({ open, onOpenChange, title, children }: { open: boolean; onOpenChange: (o: boolean) => void; title: string; children: ReactNode }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/20" />
        <Dialog.Content className="bg-surface shadow-raised-lg fixed top-0 right-0 z-50 flex h-full w-[min(92vw,420px)] flex-col gap-4 overflow-y-auto p-6">
          <Dialog.Title className="text-[15px] font-semibold">{title}</Dialog.Title>
          <Dialog.Description className="sr-only">{title}</Dialog.Description>
          {children}
          <Dialog.Close className="bg-surface shadow-raised-sm rounded-control mt-auto self-end px-4 py-2">Close</Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
