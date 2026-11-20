import { describe, expect, it } from 'vitest'
import { backoff, useRealtime } from './realtime'

describe('realtime store', () => {
  it('routes messages by channel', () => {
    const { apply } = useRealtime.getState()
    apply({ ch: 'ticker:BTCUSDT', data: { symbol: 'BTCUSDT', last: '1' } })
    apply({ ch: 'risk', data: { kill_switch: true } })
    apply({ ch: 'unknown', data: {} })
    const s = useRealtime.getState()
    expect(s.tickers.BTCUSDT.last).toBe('1')
    expect(s.risk?.kill_switch).toBe(true)
  })
  it('backs off exponentially up to 30 s', () => {
    expect([0, 1, 2, 3].map(backoff)).toEqual([1000, 2000, 4000, 8000])
    expect(backoff(20)).toBe(30_000)
  })
})
