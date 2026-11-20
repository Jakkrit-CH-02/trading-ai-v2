import { useQuery } from '@tanstack/react-query'
import { api, type Schemas } from '../../lib/api'

export const useSummary = () => useQuery({ queryKey: ['summary'], queryFn: () => api<Schemas['DashboardSummary']>('/dashboard/summary'), refetchInterval: 30_000 })
export const useWatchlist = () => useQuery({ queryKey: ['watchlist'], queryFn: () => api<Schemas['WatchItem'][]>('/watchlist'), refetchInterval: 60_000 })
export const useStats = (symbol: string) => useQuery({ queryKey: ['stats', symbol], queryFn: () => api<Schemas['MarketStats']>(`/markets/${symbol}/stats`), refetchInterval: 30_000 })
export const useCandles = (symbol: string, interval: string, limit: number) =>
  useQuery({ queryKey: ['candles', symbol, interval, limit], queryFn: () => api<Schemas['CandleOut'][]>(`/markets/${symbol}/candles?interval=${interval}&limit=${limit}`), refetchInterval: 60_000 })
export const useSentiment = () => useQuery({ queryKey: ['sentiment'], queryFn: () => api<Schemas['Sentiment']>('/sentiment'), staleTime: 600_000 })
export const useBots = () => useQuery({ queryKey: ['bots'], queryFn: () => api<Schemas['BotsSummary']>('/bots/summary') })
export const useOrders = (status: 'all' | 'open' | 'filled') =>
  useQuery({ queryKey: ['orders', status], queryFn: () => api<Schemas['OrderOut'][]>(`/orders?status=${status}`), refetchInterval: 15_000 })

/** Map a query result onto the four card states of SPEC 10.2. */
export function cardStatus(q: { isPending: boolean; isError: boolean; data?: unknown }, isEmpty?: (d: never) => boolean): 'loading' | 'error' | 'empty' | 'ready' {
  if (q.isPending) return 'loading'
  if (q.isError) return 'error'
  if (q.data == null || (isEmpty && isEmpty(q.data as never))) return 'empty'
  return 'ready'
}
