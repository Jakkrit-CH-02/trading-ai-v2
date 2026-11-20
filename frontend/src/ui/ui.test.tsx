import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { CardState, ConfirmDialog, Segmented, Signed, decimalsFromTick, fmtCompact, snapToStep } from '.'

describe('formatting', () => {
  it('snaps to tick size', () => {
    expect(snapToStep('97400.0456', 0.01)).toBe('97400.05')
    expect(snapToStep('0.10509', 0.0001)).toBe('0.1051')
    expect(snapToStep('abc', 0.01)).toBe('abc')
  })
  it('abbreviates above 6 digits and derives decimals from tick', () => {
    expect(fmtCompact(128_460)).toBe('128.5K')
    expect(fmtCompact(32_800_000)).toBe('32.8M')
    expect(fmtCompact(98.1)).toBe('98.1')
    expect(decimalsFromTick(0.01)).toBe(2)
    expect(decimalsFromTick(1)).toBe(0)
  })
})

describe('Signed', () => {
  it('always prints the sign so colour is never the only cue', () => {
    render(
      <>
        <Signed value={2.84} suffix="%" />
        <Signed value={-0.96} suffix="%" />
        <Signed value={0} />
      </>,
    )
    expect(screen.getByText('+2.84%')).toBeInTheDocument()
    expect(screen.getByText('−0.96%')).toBeInTheDocument()
    expect(screen.getByText('0.00')).toBeInTheDocument()
  })
})

describe('CardState', () => {
  it('renders each state', async () => {
    const retry = vi.fn()
    const { rerender } = render(<CardState status="loading"><p>data</p></CardState>)
    expect(screen.getByRole('status')).toBeInTheDocument()
    rerender(<CardState status="empty" empty="nothing yet"><p>data</p></CardState>)
    expect(screen.getByText('nothing yet')).toBeInTheDocument()
    rerender(<CardState status="error" onRetry={retry}><p>data</p></CardState>)
    await userEvent.click(screen.getByRole('button', { name: 'ลองใหม่' }))
    expect(retry).toHaveBeenCalled()
    rerender(<CardState status="ready"><p>data</p></CardState>)
    expect(screen.getByText('data')).toBeInTheDocument()
  })
})

describe('Segmented', () => {
  it('exposes a radiogroup and reports selection', async () => {
    const onChange = vi.fn()
    render(<Segmented label="Range" options={['1H', '4H'] as const} value="1H" onChange={onChange} />)
    expect(screen.getByRole('radio', { name: '1H' })).toBeChecked()
    await userEvent.click(screen.getByRole('radio', { name: '4H' }))
    expect(onChange).toHaveBeenCalledWith('4H')
  })
})

describe('ConfirmDialog', () => {
  it('only enables confirm with a 6-digit TOTP and passes it on', async () => {
    const onConfirm = vi.fn()
    render(<ConfirmDialog open onOpenChange={() => {}} title="Reset kill switch" requireTotp confirmLabel="Reset" onConfirm={onConfirm} />)
    const btn = screen.getByRole('button', { name: 'Reset' })
    expect(btn).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/TOTP/), '12a345')
    expect(btn).toBeDisabled() // non-digits stripped -> only 5 digits
    await userEvent.type(screen.getByLabelText(/TOTP/), '6')
    expect(btn).toBeEnabled()
    await userEvent.click(btn)
    expect(onConfirm).toHaveBeenCalledWith('123456')
  })
})

describe('NumberInput', () => {
  it('does not rewrite a value that is already on the tick grid when it loses focus', async () => {
    const { NumberInput } = await import('.')
    const seen: string[] = []
    render(<NumberInput label="Price" unit="USDT" value="115" step={0.01} onChange={(v) => seen.push(v)} />)
    const input = screen.getByLabelText(/Price/)
    input.focus()
    input.blur()
    expect(seen).toEqual([]) // "115" -> "115.00" would silently change submitted values
    seen.length = 0
    render(<NumberInput label="Qty" unit="BTC" value="0.10509" step={0.0001} onChange={(v) => seen.push(v)} />)
    const q = screen.getByLabelText(/Qty/)
    q.focus()
    q.blur()
    expect(seen).toEqual(['0.1051']) // a real off-grid value is still snapped
  })
})
