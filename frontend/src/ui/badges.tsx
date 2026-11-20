import { cx } from './cx'

export type OrderStatus = 'Filled' | 'Open' | 'Cancelled'

export function StatusBadge({ status }: { status: OrderStatus }) {
  return (
    <span
      className={cx(
        'inline-block rounded-full px-3 py-0.5 text-[11px] leading-4 font-semibold',
        status === 'Open' && 'bg-accent text-on-accent',
        status === 'Filled' && 'shadow-raised-sm text-primary',
        status === 'Cancelled' && 'shadow-raised-sm text-secondary font-normal',
      )}
    >
      {status}
    </span>
  )
}

export function MarketStatusPill({ open = true }: { open?: boolean }) {
  return (
    <span className="shadow-raised-sm inline-flex items-center gap-2 rounded-full px-4 py-2 text-[11px]">
      <span aria-hidden className={cx('size-2 rounded-full', open ? 'bg-up' : 'bg-down')} />
      {open ? 'Market open' : 'Market closed'}
    </span>
  )
}

export type BotStatus = 'RUNNING' | 'PAUSED' | 'KILLED'

export function BotStatusPill({ status, label }: { status: BotStatus; label?: string }) {
  return (
    <span
      className={cx(
        'shadow-raised-sm inline-flex items-center gap-2 rounded-full px-3 py-1 text-[11px] font-semibold',
        status === 'KILLED' ? 'text-down' : 'text-primary',
      )}
    >
      <span aria-hidden className={cx('size-2 rounded-full', status === 'RUNNING' ? 'bg-up' : status === 'PAUSED' ? 'bg-accent' : 'bg-down')} />
      {label ?? status}
    </span>
  )
}

/** Signed number: always shows + or − so colour is never the only cue (SPEC 9.1). */
export function Signed({ value, suffix = '', digits = 2 }: { value: number; suffix?: string; digits?: number }) {
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  return (
    <span className={value > 0 ? 'text-up' : value < 0 ? 'text-down' : 'text-secondary'}>
      {sign}
      {Math.abs(value).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}
      {suffix}
    </span>
  )
}
