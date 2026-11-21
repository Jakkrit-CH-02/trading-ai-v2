import { refresh, useAuth } from '../../lib/auth'
import type { ChatEvent, ChatMessage } from './queries'

/** Parse a Server-Sent-Events body into events. Exported for tests. */
export function parseSse(buffer: string): { events: ChatEvent[]; rest: string } {
  const parts = buffer.split('\n\n')
  const rest = parts.pop() ?? ''
  const events: ChatEvent[] = []
  for (const p of parts) {
    const line = p.split('\n').find((l) => l.startsWith('data: '))
    if (!line) continue
    try {
      events.push(JSON.parse(line.slice(6)) as ChatEvent)
    } catch {
      /* a broken frame is skipped, not fatal */
    }
  }
  return { events, rest }
}

async function post(messages: ChatMessage[], signal?: AbortSignal): Promise<Response> {
  const token = useAuth.getState().token
  return fetch('/api/v1/ai/chat', {
    method: 'POST',
    signal,
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify({ messages }),
  })
}

/** POST /ai/chat and call `onEvent` for every streamed event. Never throws: failures become an error event. */
export async function streamChat(messages: ChatMessage[], onEvent: (e: ChatEvent) => void, signal?: AbortSignal): Promise<void> {
  try {
    let res = await post(messages, signal)
    if (res.status === 401 && (await refresh())) res = await post(messages, signal)
    if (!res.ok || !res.body) {
      let msg = `${res.status}`
      try {
        msg = ((await res.json()) as { detail?: string }).detail ?? msg
      } catch {
        /* keep the status */
      }
      onEvent({ type: 'error', message: res.status === 503 ? 'AI ยังไม่พร้อม: ตรวจ ai-worker และ ANTHROPIC_API_KEY' : res.status === 429 ? 'ถามเกินโควตาต่อชั่วโมงแล้ว' : msg })
      return
    }
    const reader = res.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const { events, rest } = parseSse(buf)
      buf = rest
      events.forEach(onEvent)
    }
  } catch (e) {
    if ((e as Error).name !== 'AbortError') onEvent({ type: 'error', message: 'เชื่อมต่อ AI ไม่ได้' })
  }
}
