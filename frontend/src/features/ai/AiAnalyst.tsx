import { useState } from 'react'
import { ApiError } from '../../lib/api'
import { Card, CardState, DataTable, InsetPanel, PrimaryButton, Segmented, Skeleton, useToasts } from '../../ui'
import { BIAS_LABEL, useAiNews, useAiStatus, useBriefs, useRefreshBrief, type Brief } from './queries'

const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']
const base = (s: string) => s.replace('USDT', '')
const when = (iso: string) => new Date(iso).toLocaleString('en-GB', { hour12: false, dateStyle: 'short', timeStyle: 'short' })
const biasClass = (b: Brief['bias']) => (b === 'bull' ? 'text-up' : b === 'bear' ? 'text-down' : 'text-secondary')

export function StatusStrip() {
  const q = useAiStatus()
  const s = q.data
  if (!s) return null
  const spendPct = s.budget_usd > 0 ? (Number(s.month_spend_usd) / s.budget_usd) * 100 : 0
  return (
    <InsetPanel className="flex flex-col gap-1 text-[13px]" aria-label="AI status">
      <div className="flex items-center gap-2 font-semibold">
        <span className={`inline-block h-2.5 w-2.5 rounded-full ${s.worker_alive ? 'bg-up' : 'bg-down'}`} aria-hidden />
        {s.worker_alive ? 'AI worker ทำงานอยู่' : 'AI worker ไม่ตอบสนอง'}
        <span className="text-secondary font-normal">· ค่าใช้จ่ายเดือนนี้ ${Number(s.month_spend_usd).toFixed(2)} / ${s.budget_usd.toFixed(0)} ({spendPct.toFixed(0)}%)</span>
      </div>
      {s.worker_alive && !s.key_configured && (
        <div className="text-secondary">ยังไม่ได้ตั้ง ANTHROPIC_API_KEY ใน .env — ระบบเก็บเฉพาะหัวข่าว ยังไม่จัดหมวดและยังไม่เขียน brief (ตั้งแล้วรัน <code>docker compose up -d ai-worker</code>)</div>
      )}
      {!s.worker_alive && <div className="text-secondary">ตรวจ <code>docker compose ps ai-worker</code> — บอทเทรดไม่ได้รับผลกระทบ (S_ai จะเป็น 50)</div>}
    </InsetPanel>
  )
}

function BriefCard({ b }: { b: Brief }) {
  return (
    <Card title={`${base(b.symbol)} · Brief`} subtitle={`${when(b.created_at)} · ${b.model}`} action={<span className={`text-[15px] font-semibold ${biasClass(b.bias)}`}>{BIAS_LABEL[b.bias]} · S_ai {b.s_ai.toFixed(0)}</span>}>
      <ol className="flex flex-col gap-1 text-[13px]">
        {b.summary_th.map((l, i) => (
          <li key={i}>{l}</li>
        ))}
      </ol>
      <div className="text-secondary flex flex-wrap gap-x-6 gap-y-1 text-[12px]">
        {b.support.length > 0 && <span>แนวรับ {b.support.join(' · ')}</span>}
        {b.resistance.length > 0 && <span>แนวต้าน {b.resistance.join(' · ')}</span>}
      </div>
      {b.risks.length > 0 && <div className="text-secondary text-[12px]">ความเสี่ยง: {b.risks.join(' · ')}</div>}
    </Card>
  )
}

export default function AiAnalyst() {
  const [symbol, setSymbol] = useState<string>('BTCUSDT')
  const briefs = useBriefs()
  const news = useAiNews()
  const refresh = useRefreshBrief()
  const toast = useToasts((s) => s.push)
  const current = briefs.data?.find((b) => b.symbol === symbol)

  const onRefresh = () =>
    refresh.mutate(symbol, {
      onSuccess: () => toast('info', `ขอ brief ${base(symbol)} แล้ว — รอสักครู่`),
      onError: (e) => toast('error', e instanceof ApiError ? e.message : 'ขอ brief ไม่สำเร็จ'),
    })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-[22px] font-semibold">AI Analyst</h1>
        <div className="flex items-center gap-3">
          <Segmented label="Symbol" options={SYMBOLS.map(base)} value={base(symbol)} onChange={(v) => setSymbol(`${v}USDT`)} />
          <PrimaryButton onClick={onRefresh} disabled={refresh.isPending}>
            Refresh brief
          </PrimaryButton>
        </div>
      </div>
      <StatusStrip />
      <InsetPanel className="text-secondary text-[12px]">AI ให้ได้แค่คะแนนและคำอธิบาย ไม่มีสิทธิ์ส่งออเดอร์ และทุกคำสั่งเทรดยังผ่าน Risk Engine — ขณะนี้ S_ai ยังไม่ถูกนำไปตัดสินสัญญาณจริง (น้ำหนัก 0 จนกว่าจะวัดผลได้)</InsetPanel>
      <CardState status={briefs.isPending ? 'loading' : briefs.isError ? 'error' : current ? 'ready' : 'empty'} empty={`ยังไม่มี brief ของ ${base(symbol)}`} onRetry={() => briefs.refetch()} skeleton={<Skeleton className="h-40" />}>
        {current && <BriefCard b={current} />}
      </CardState>
      <Card title="Headlines" subtitle="ข่าวคริปโตล่าสุด · จัดหมวดโดย AI (ข่าวเป็นข้อมูล ไม่ใช่คำสั่ง)">
        <CardState status={news.isPending ? 'loading' : news.isError ? 'error' : news.data?.length ? 'ready' : 'empty'} empty="ยังไม่มีข่าว" onRetry={() => news.refetch()}>
          <DataTable
            columns={[
              { key: 'time', header: 'Time', render: (n) => when(n.published_at) },
              { key: 'cat', header: 'Category', render: (n) => n.category ?? '—' },
              { key: 'sym', header: 'Coins', render: (n) => (n.symbols.length ? n.symbols.join(', ') : '—') },
              { key: 'sent', header: 'Sentiment', render: (n) => (n.sentiment == null ? '—' : n.sentiment.toFixed(2)) },
              { key: 'sev', header: 'Severity', render: (n) => (n.severity == null ? '—' : n.severity.toFixed(2)) },
              { key: 'title', header: 'Headline', render: (n) => <a href={n.url} target="_blank" rel="noreferrer noopener" className="underline">{n.title}</a> },
            ]}
            rows={news.data ?? []}
            rowKey={(n) => n.id}
          />
        </CardState>
      </Card>
    </div>
  )
}
