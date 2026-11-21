import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Schemas } from '../../lib/api'

export type Brief = Schemas['BriefOut']
export type News = Schemas['NewsOut']
export type AiStatus = Schemas['AiStatus']

export const useBriefs = (symbol?: string) =>
  useQuery({ queryKey: ['ai-briefs', symbol ?? 'all'], queryFn: () => api<Brief[]>(`/ai/briefs${symbol ? `?symbol=${symbol}` : ''}`), refetchInterval: 60_000 })
export const useAiNews = (symbol?: string) =>
  useQuery({ queryKey: ['ai-news', symbol ?? 'all'], queryFn: () => api<News[]>(`/ai/news?limit=30${symbol ? `&symbol=${symbol}` : ''}`), refetchInterval: 60_000 })
export const useAiStatus = () => useQuery({ queryKey: ['ai-status'], queryFn: () => api<AiStatus>('/ai/status'), refetchInterval: 30_000 })
export const useRefreshBrief = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (symbol: string) => api<{ status: string }>('/ai/briefs/refresh', { method: 'POST', body: JSON.stringify({ symbol }), headers: { 'Content-Type': 'application/json' } }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['ai-status'] }),
  })
}

export const BIAS_LABEL: Record<Brief['bias'], string> = { bull: 'Bullish', neutral: 'Neutral', bear: 'Bearish' }
