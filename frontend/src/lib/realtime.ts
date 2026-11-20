import { useEffect } from 'react'
import { create } from 'zustand'
import type { Schemas } from './api'

type Ticker = Schemas['MarketStats'] // the ticker channel carries the stats fields
type Summary = Schemas['DashboardSummary']
type Risk = Schemas['RiskStatus']
export type WsStatus = 'connecting' | 'open' | 'closed'

type State = {
  status: WsStatus
  tickers: Record<string, Ticker>
  portfolio: Summary | null
  risk: Risk | null
  apply: (msg: { ch: string; data: unknown }) => void
  setStatus: (s: WsStatus) => void
}

export const useRealtime = create<State>((set) => ({
  status: 'closed',
  tickers: {},
  portfolio: null,
  risk: null,
  setStatus: (status) => set({ status }),
  apply: ({ ch, data }) => {
    if (ch.startsWith('ticker:')) set((s) => ({ tickers: { ...s.tickers, [ch.slice(7)]: data as Ticker } }))
    else if (ch === 'portfolio') set({ portfolio: data as Summary })
    else if (ch === 'risk') set({ risk: data as Risk })
  },
}))

export const backoff = (attempt: number) => Math.min(30_000, 1000 * 2 ** attempt)

/** One multiplexed socket per tab; reconnects with exponential backoff and re-subscribes. */
export function useRealtimeConnection(channels: string[]) {
  const key = channels.join('|')
  useEffect(() => {
    let ws: WebSocket | null = null
    let attempt = 0
    let timer: ReturnType<typeof setTimeout> | undefined
    let stopped = false
    const { apply, setStatus } = useRealtime.getState()
    const connect = () => {
      setStatus('connecting')
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws`)
      ws.onopen = () => {
        attempt = 0
        setStatus('open')
        ws?.send(JSON.stringify({ op: 'subscribe', channels: key.split('|').filter(Boolean) }))
      }
      ws.onmessage = (e) => {
        try {
          apply(JSON.parse(String(e.data)))
        } catch {
          /* ignore malformed frame */
        }
      }
      ws.onclose = () => {
        setStatus('closed')
        if (!stopped) timer = setTimeout(connect, backoff(attempt++))
      }
    }
    connect()
    return () => {
      stopped = true
      clearTimeout(timer)
      ws?.close()
    }
  }, [key])
}
