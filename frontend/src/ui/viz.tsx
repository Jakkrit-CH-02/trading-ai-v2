import { useEffect, useRef } from 'react'
import { cx } from './cx'
import { fmtPrice } from './format'
import { Signed } from './badges'

export function Sparkline({ points, className }: { points: number[]; className?: string }) {
  if (points.length < 2) return <svg aria-hidden className={cx('h-6 w-16', className)} />
  const min = Math.min(...points)
  const span = Math.max(...points) - min || 1
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${(i / (points.length - 1)) * 64},${22 - ((p - min) / span) * 20}`).join(' ')
  const up = points[points.length - 1] >= points[0]
  return (
    <svg aria-hidden viewBox="0 0 64 24" className={cx('h-6 w-16', up ? 'text-up' : 'text-down', className)}>
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function AssetRow({
  symbol,
  name,
  price,
  change,
  spark,
  decimals = 2,
  onClick,
  selected,
}: {
  symbol: string
  name: string
  price: number
  change: number
  spark: number[]
  decimals?: number
  onClick?: () => void
  selected?: boolean
}) {
  const flash = useRef<HTMLSpanElement>(null)
  const prev = useRef(price)
  useEffect(() => {
    const el = flash.current
    if (el && price !== prev.current) {
      el.classList.remove('flash-up', 'flash-down')
      void el.offsetWidth
      el.classList.add(price > prev.current ? 'flash-up' : 'flash-down')
    }
    prev.current = price
  }, [price])
  return (
    <button
      onClick={onClick}
      aria-pressed={selected}
      className={cx('bg-surface rounded-panel flex w-full items-center gap-3 px-4 py-3 text-left', selected ? 'shadow-pressed' : 'shadow-raised-sm')}
    >
      <span className="shadow-inset grid size-8 place-items-center rounded-full text-[13px] font-semibold">{symbol[0]}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-[13px] leading-5 font-semibold">{symbol}</span>
        <span className="text-secondary block truncate text-[11px] leading-4">{name}</span>
      </span>
      <Sparkline points={spark} />
      <span className="min-w-[84px] text-right">
        <span ref={flash} className="block text-[13px] leading-5 font-semibold">
          ${fmtPrice(price, decimals)}
        </span>
        <span className="block text-[11px] leading-4 font-semibold">
          <Signed value={change} suffix="%" />
        </span>
      </span>
    </button>
  )
}

export function AllocationBars({ items }: { items: { label: string; pct: number }[] }) {
  return (
    <div className="flex justify-between gap-3">
      {items.map((i) => (
        <div key={i.label} className="flex flex-1 flex-col items-center gap-2">
          <div
            role="img"
            aria-label={`${i.label} ${i.pct}%`}
            className="shadow-inset relative flex h-[90px] w-full max-w-9 items-end rounded-full p-[3px]"
          >
            <div className="bg-accent text-on-accent grid w-full place-items-center rounded-full text-[10px] font-semibold" style={{ height: `${Math.max(i.pct, 14)}%` }}>
              {i.pct}%
            </div>
          </div>
          <span className="text-secondary text-[11px]">{i.label}</span>
        </div>
      ))}
    </div>
  )
}

/** Half-circle tick gauge for the Fear & Greed index (0–100). */
export function Gauge({ value, label }: { value: number; label: string }) {
  const ticks = 40
  const v = Math.max(0, Math.min(100, value))
  return (
    <div className="relative mx-auto w-[220px]" role="img" aria-label={`${label} ${v}`}>
      <svg viewBox="-110 -110 220 120" className="w-full">
        {Array.from({ length: ticks + 1 }, (_, i) => {
          const a = Math.PI * (1 - i / ticks)
          const long = i % 5 === 0
          const r1 = 100
          const r2 = long ? 82 : 88
          const active = (i / ticks) * 100 <= v
          return (
            <line
              key={i}
              x1={Math.cos(a) * r1}
              y1={-Math.sin(a) * r1}
              x2={Math.cos(a) * r2}
              y2={-Math.sin(a) * r2}
              stroke={active ? 'var(--text-primary)' : 'var(--shadow-dark)'}
              strokeWidth={2}
              strokeLinecap="round"
            />
          )
        })}
      </svg>
      <div className="absolute inset-x-0 bottom-0 text-center">
        <div className="text-[32px] leading-9 font-bold">{v}</div>
        <div className="text-[13px] font-medium">{label}</div>
      </div>
    </div>
  )
}
