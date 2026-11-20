import type { HTMLAttributes, ReactNode } from 'react'
import { cx } from './cx'

type CardProps = {
  title?: ReactNode
  subtitle?: ReactNode
  action?: ReactNode
  children?: ReactNode
  className?: string
}

export function Card({ title, subtitle, action, children, className }: CardProps) {
  return (
    <section className={cx('bg-surface shadow-raised-lg rounded-card flex flex-col gap-4 p-6', className)}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-[15px] leading-5 font-semibold">{title}</h2>}
            {subtitle && <p className="text-secondary text-[11px] leading-4">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  )
}

export function InsetPanel({ className, ...p }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cx('shadow-inset rounded-panel p-4', className)} {...p} />
}

export function StatTile({ label, value, className }: { label: string; value: ReactNode; className?: string }) {
  return (
    <InsetPanel className={cx('flex flex-col', className)}>
      <span className="text-secondary text-[11px] leading-4">{label}</span>
      <span className="text-[13px] leading-5 font-semibold">{value}</span>
    </InsetPanel>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx('skeleton shadow-inset rounded-panel', className)} />
}

/** loading / empty / error shell shared by every data card (SPEC 10.2). */
export function CardState({
  status,
  empty,
  error,
  onRetry,
  skeleton,
  children,
}: {
  status: 'loading' | 'empty' | 'error' | 'ready'
  empty?: ReactNode
  error?: ReactNode
  onRetry?: () => void
  skeleton?: ReactNode
  children: ReactNode
}) {
  if (status === 'loading') return <div role="status" aria-label="Loading">{skeleton ?? <Skeleton className="h-24" />}</div>
  if (status === 'error')
    return (
      <InsetPanel role="alert" className="text-down flex flex-col items-start gap-2">
        <span>{error ?? 'โหลดข้อมูลไม่สำเร็จ'}</span>
        {onRetry && (
          <button onClick={onRetry} className="bg-surface shadow-raised-sm text-primary rounded-full px-3 py-1 text-[11px]">
            ลองใหม่
          </button>
        )}
      </InsetPanel>
    )
  if (status === 'empty') return <InsetPanel className="text-secondary">{empty ?? 'ยังไม่มีข้อมูล'}</InsetPanel>
  return <>{children}</>
}
