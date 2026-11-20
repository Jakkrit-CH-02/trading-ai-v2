import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { cx } from './cx'

export function PrimaryButton({ className, ...p }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={cx(
        'bg-accent text-on-accent shadow-raised-sm rounded-control px-6 py-3 text-[15px] font-semibold active:shadow-pressed disabled:opacity-50',
        className,
      )}
      {...p}
    />
  )
}

export function IconButton({
  icon,
  label,
  showLabel,
  className,
  ...p
}: { icon: ReactNode; label: string; showLabel?: boolean } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <span className="inline-flex flex-col items-center gap-1">
      <button
        aria-label={label}
        className={cx('bg-surface shadow-raised-sm text-primary grid size-11 place-items-center rounded-full active:shadow-pressed', className)}
        {...p}
      >
        {icon}
      </button>
      {showLabel && <span className="text-secondary text-[11px] leading-4">{label}</span>}
    </span>
  )
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
  className,
}: {
  options: readonly T[]
  value: T
  onChange: (v: T) => void
  label: string
  className?: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cx('shadow-inset inline-flex rounded-full p-1', className)}>
      {options.map((o) => (
        <button
          key={o}
          role="radio"
          aria-checked={o === value}
          onClick={() => onChange(o)}
          className={cx(
            'rounded-full px-3 py-1 text-[11px] leading-4 font-medium',
            o === value ? 'shadow-pressed text-primary font-semibold' : 'text-secondary',
          )}
        >
          {o}
        </button>
      ))}
    </div>
  )
}

export function PercentChips({ value, onChange, options = [25, 50, 75, 100] }: { value?: number; onChange: (p: number) => void; options?: number[] }) {
  return (
    <div className="grid grid-cols-4 gap-3">
      {options.map((p) => (
        <button
          key={p}
          aria-pressed={p === value}
          onClick={() => onChange(p)}
          className={cx('bg-surface rounded-full py-2 text-[13px]', p === value ? 'shadow-pressed font-semibold' : 'shadow-raised-sm')}
        >
          {p}%
        </button>
      ))}
    </div>
  )
}

/** Rounds to the symbol's tick/step size so the user cannot type an invalid precision. */
export function snapToStep(value: string, step: number): string {
  const n = Number(value)
  if (!Number.isFinite(n) || step <= 0) return value
  const decimals = Math.max(0, Math.round(-Math.log10(step)))
  return (Math.round(n / step) * step).toFixed(decimals)
}

export function NumberInput({
  label,
  unit,
  value,
  onChange,
  step,
}: {
  label: string
  unit: string
  value: string
  onChange: (v: string) => void
  step?: number
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-secondary text-[11px] leading-4">{label}</span>
      <span className="shadow-inset rounded-control flex items-center px-4 py-3">
        <input
          inputMode="decimal"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={() => {
            // only rewrite when snapping changes the number: "115" -> "115.00" would needlessly
            // change what is submitted (and re-run dependent previews) the moment a button is clicked
            if (!step) return
            const snapped = snapToStep(value, step)
            if (Number(snapped) !== Number(value)) onChange(snapped)
          }}
          className="w-full bg-transparent text-[15px] font-medium outline-none"
        />
        <span className="text-secondary text-[11px]">{unit}</span>
      </span>
    </label>
  )
}

export function Slider({
  label,
  value,
  min,
  max,
  step,
  unit = '%',
  onChange,
  hint,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  unit?: string
  onChange: (v: number) => void
  hint?: string
}) {
  return (
    <label className="flex flex-col gap-2">
      <span className="flex items-baseline justify-between">
        <span className="text-[13px] font-medium">{label}</span>
        <span className="text-[13px] font-semibold">
          {value}
          {unit}
        </span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="accent-[var(--accent)] w-full"
      />
      {hint && <span className="text-secondary text-[11px]">{hint}</span>}
    </label>
  )
}

export function TextInput({ label, ...p }: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-secondary text-[11px] leading-4">{label}</span>
      <input {...p} className={cx('shadow-inset rounded-control w-full bg-transparent px-4 py-3 outline-none', p.className)} />
    </label>
  )
}
