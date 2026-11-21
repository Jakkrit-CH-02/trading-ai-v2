import { useQuery } from '@tanstack/react-query'
import { api, type Schemas } from '../../lib/api'

export type Bot = Schemas['BotDetail']
export type Performance = Schemas['PerformanceOut']
export type Signal = Schemas['SignalOut']

export const useBotList = () => useQuery({ queryKey: ['bot-list'], queryFn: () => api<Bot[]>('/bots'), refetchInterval: 15_000 })
export const useBot = (id: string) => useQuery({ queryKey: ['bot', id], queryFn: () => api<Bot>(`/bots/${id}`), refetchInterval: 15_000 })
export const useGates = (id: string) => useQuery({ queryKey: ['gates', id], queryFn: () => api<Schemas['GatesOut']>(`/bots/${id}/gates`) })
export const usePerformance = (id: string) => useQuery({ queryKey: ['perf', id], queryFn: () => api<Performance>(`/bots/${id}/performance`), refetchInterval: 30_000 })
export const useSignals = (id: string, decision?: string) =>
  useQuery({ queryKey: ['signals', id, decision], queryFn: () => api<Signal[]>(`/signals?bot_id=${id}${decision ? `&decision=${decision}` : ''}`) })
export const useBotTrades = (id: string) => useQuery({ queryKey: ['bot-trades', id], queryFn: () => api<Schemas['TradeOut'][]>(`/trades?bot_id=${id}`) })
export const useBotLogs = (id: string) =>
  useQuery({ queryKey: ['bot-logs', id], queryFn: () => api<Schemas['LogEntryOut'][]>(`/bots/${id}/logs?limit=200`), refetchInterval: 10_000 })
export const useRunner = () =>
  useQuery({ queryKey: ['runner'], queryFn: () => api<Schemas['RunnerStatus']>('/runner/status'), refetchInterval: 10_000 })
export const useStrategies = () => useQuery({ queryKey: ['strategies'], queryFn: () => api<Schemas['StrategyPreset'][]>('/strategies'), staleTime: Infinity })
export const useAccounts = () => useQuery({ queryKey: ['accounts'], queryFn: () => api<Schemas['AccountOut'][]>('/accounts') })

export const STATUS_PILL = (s: string): 'RUNNING' | 'PAUSED' | 'KILLED' => (s === 'KILLED' ? 'KILLED' : s === 'PAPER' || s === 'RUNNING' ? 'RUNNING' : 'PAUSED')
