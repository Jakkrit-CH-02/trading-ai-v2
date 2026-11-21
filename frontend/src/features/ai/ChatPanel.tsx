import { useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { api, ApiError } from '../../lib/api'
import { Card, InsetPanel, PrimaryButton, useToasts } from '../../ui'
import { streamChat } from './chat'
import type { ChatEvent, ChatMessage } from './queries'

type Proposal = Extract<ChatEvent, { type: 'proposal' }>
type Turn = ChatMessage & { tools?: string[]; error?: string; proposals?: Proposal[] }

const TOOL_LABEL: Record<string, string> = {
  get_positions: 'ตรวจสถานะที่เปิดอยู่',
  get_bot_stats: 'ดูสถิติบอท',
  get_analysis: 'อ่าน brief และข่าว',
  get_recent_signals: 'ดูสัญญาณล่าสุด',
  propose_pause_bot: 'เสนอให้หยุดบอท',
}

function ProposalBox({ p }: { p: Proposal }) {
  const qc = useQueryClient()
  const toast = useToasts((s) => s.push)
  const [state, setState] = useState<'open' | 'done' | 'dismissed'>('open')
  const pause = async () => {
    try {
      await api(`/bots/${p.bot_id}/pause`, { method: 'POST' })
      setState('done')
      void qc.invalidateQueries({ queryKey: ['bot-list'] })
      toast('info', `หยุดบอท ${p.bot_name} แล้ว`)
    } catch (e) {
      toast('error', e instanceof ApiError ? e.message : 'หยุดบอทไม่สำเร็จ')
    }
  }
  if (state === 'dismissed') return null
  return (
    <InsetPanel role="group" aria-label="AI proposal" className="flex flex-col gap-2 text-[13px]">
      <div>
        <strong>AI เสนอให้หยุดบอท {p.bot_name}</strong> — {p.reason}
      </div>
      {state === 'done' ? (
        <div className="text-secondary">หยุดแล้ว (ตามที่คุณยืนยัน)</div>
      ) : (
        <div className="flex gap-3">
          <PrimaryButton onClick={() => void pause()}>ยืนยัน Pause</PrimaryButton>
          <button className="text-secondary underline" onClick={() => setState('dismissed')}>
            ไม่ต้อง
          </button>
        </div>
      )}
      <div className="text-secondary text-[11px]">AI เปลี่ยนอะไรเองไม่ได้ — ต้องกดยืนยันเสมอ</div>
    </InsetPanel>
  )
}

export default function ChatPanel() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const abort = useRef<AbortController | null>(null)

  const patchLast = (f: (t: Turn) => Turn) => setTurns((ts) => ts.map((t, i) => (i === ts.length - 1 ? f(t) : t)))

  const send = async () => {
    const q = input.trim()
    if (!q || busy) return
    const history: ChatMessage[] = [...turns.filter((t) => !t.error).map(({ role, content }) => ({ role, content })), { role: 'user', content: q }]
    setTurns((ts) => [...ts, { role: 'user', content: q }, { role: 'assistant', content: '' }])
    setInput('')
    setBusy(true)
    abort.current = new AbortController()
    await streamChat(
      history,
      (e) => {
        if (e.type === 'delta') patchLast((t) => ({ ...t, content: t.content + e.text }))
        else if (e.type === 'tool') patchLast((t) => ({ ...t, tools: [...(t.tools ?? []), e.name] }))
        else if (e.type === 'proposal') patchLast((t) => ({ ...t, proposals: [...(t.proposals ?? []), e] }))
        else if (e.type === 'error') patchLast((t) => ({ ...t, error: e.message }))
      },
      abort.current.signal,
    )
    setBusy(false)
  }

  return (
    <Card title="AI Chat" subtitle="ถามเรื่องพอร์ตและบอท · AI อ่านข้อมูลได้อย่างเดียว ไม่แนะนำให้ซื้อขาย">
      <div className="flex max-h-[420px] flex-col gap-3 overflow-y-auto" aria-live="polite">
        {turns.length === 0 && <InsetPanel className="text-secondary text-[13px]">ลองถาม: “บอทตอนนี้เป็นยังไงบ้าง” · “ทำไมสัญญาณล่าสุดถูกข้าม” · “มีสถานะไหนเสี่ยงอยู่ไหม”</InsetPanel>}
        {turns.map((t, i) => (
          <div key={i} className={t.role === 'user' ? 'self-end' : ''}>
            <InsetPanel className={`text-[13px] whitespace-pre-wrap ${t.role === 'user' ? 'text-secondary' : ''}`}>
              {t.tools?.length ? <div className="text-secondary mb-1 text-[11px]">{t.tools.map((n) => TOOL_LABEL[n] ?? n).join(' · ')}</div> : null}
              {t.content || (t.role === 'assistant' && !t.error && busy && i === turns.length - 1 ? '…' : '')}
              {t.error && <div className="text-down mt-1">{t.error}</div>}
            </InsetPanel>
            {t.proposals?.map((p, j) => <ProposalBox key={j} p={p} />)}
          </div>
        ))}
      </div>
      <form
        className="flex gap-3"
        onSubmit={(e) => {
          e.preventDefault()
          void send()
        }}
      >
        <input aria-label="Ask the AI" value={input} maxLength={4000} onChange={(e) => setInput(e.target.value)} placeholder="พิมพ์คำถาม…" className="shadow-inset rounded-control w-full bg-transparent px-4 py-3 outline-none" />
        <PrimaryButton type="submit" disabled={busy || !input.trim()}>
          Send
        </PrimaryButton>
      </form>
    </Card>
  )
}
