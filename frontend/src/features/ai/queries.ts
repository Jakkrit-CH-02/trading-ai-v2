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

export type Review = Schemas['ReviewOut']
export const useReviews = () => useQuery({ queryKey: ['ai-reviews'], queryFn: () => api<Review[]>('/ai/reviews?limit=30'), refetchInterval: 120_000 })

export type ChatMessage = { role: 'user' | 'assistant'; content: string }
export type ChatEvent =
  | { type: 'delta'; text: string }
  | { type: 'tool'; name: string }
  | { type: 'proposal'; action: 'pause_bot'; bot_id: string; bot_name: string; reason: string }
  | { type: 'done' }
  | { type: 'error'; message: string }
