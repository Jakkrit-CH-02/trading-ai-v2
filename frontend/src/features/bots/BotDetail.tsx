import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, num, type Schemas } from '../../lib/api'
import { askTotp } from '../../lib/totp'
import {
  BotStatusPill, Card, CardState, DataTable, Drawer, InsetPanel, LineChart, PrimaryButton, Segmented, Signed, Skeleton, StatTile, TextInput, fmtPrice, useToasts,
} from '../../ui'
import { STATUS_PILL, useBot, useBotTrades, useGates, usePerformance, useSignals, type Signal } from './queries'

const JSON_HEADERS = { 'Content-Type': 'application/json' }
const errText = (e: unknown) => (e instanceof ApiError ? e.message : 'เกิดข้อผิดพลาด')

function Controls({ id, status }: { id: string; status: string }) {
  const qc = useQueryClient()
  const act = useMutation({
    mutationFn: (a: 'start' | 'pause' | 'stop') => api(`/bots/${id}/${a}`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bot', id] }),
    onError: (e) => useToasts.getState().push('error', errText(e)),
  })
  const running = status === 'PAPER' || status === 'RUNNING'
  const btn = 'bg-surface shadow-raised-sm rounded-control px-5 py-2 disabled:opacity-50'
  return (
    <div className="flex gap-3">
      {running ? (
        <button className={btn} onClick={() => act.mutate('pause')}>Pause</button>
      ) : (
        <PrimaryButton disabled={status === 'KILLED' || act.isPending} onClick={() => act.mutate('start')}>Start paper</PrimaryButton>
      )}
      <button className={btn} disabled={status === 'DRAFT' || status === 'KILLED'} onClick={() => act.mutate('stop')}>Stop</button>
    </div>
  )
}

function GatesCard({ id, status }: { id: string; status: string }) {
  const qc = useQueryClient()
  const q = useGates(id)
  const live = useMutation({
    mutationFn: async () => {
      const totp = await askTotp('Go live', 'บอทจะเทรดด้วยเงินจริง — ต้องผ่านทุกเกณฑ์และใช้ 2FA')
      return totp ? api(`/bots/${id}/go-live`, { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ confirm: true }), totp }) : null
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bot', id] }),
    onError: (e) => useToasts.getState().push('error', errText(e)),
  })
  return (
    <Card title="Go-live gate" subtitle="Backtest (Gate 1) → Paper ≥ 4 สัปดาห์ (Gate 2) → เปิด Live (Gate B)">
      <CardState status={q.isPending ? 'loading' : q.isError ? 'error' : 'ready'} onRetry={() => q.refetch()} skeleton={<Skeleton className="h-32" />}>
        {q.data && (
          <>
            <ul className="flex flex-col gap-2">
              {q.data.checks.map((c) => (
                <li key={c.name} className="flex items-start gap-2 text-[13px]">
                  <span aria-label={c.ok ? 'passed' : 'not passed'} className={c.ok ? 'text-up' : 'text-down'}>{c.ok ? '✓' : '✗'}</span>
                  <span>
                    <strong>{c.name.replace(/_/g, ' ')}</strong>
                    <span className="text-secondary block text-[11px]">{c.detail}</span>
                  </span>
                </li>
              ))}
            </ul>
            <PrimaryButton disabled={!q.data.allowed || (status !== 'PAPER' && status !== 'PAUSED') || live.isPending} onClick={() => live.mutate()} title={q.data.allowed ? '' : 'ยังไม่ผ่านเกณฑ์ทุกข้อ'}>
              Go live
            </PrimaryButton>
          </>
        )}
      </CardState>
    </Card>
  )
}

function ConfigCard({ bot }: { bot: Schemas['BotDetail'] }) {
  const qc = useQueryClient()
  const [edit, setEdit] = useState<Record<string, string>>({})
  const params = (bot.config?.params ?? {}) as Record<string, number>
  const save = useMutation({
    mutationFn: () => {
      const merged = { ...params, ...Object.fromEntries(Object.entries(edit).map(([k, v]) => [k, Number(v)])) }
      return api(`/bots/${bot.id}`, { method: 'PATCH', headers: JSON_HEADERS, body: JSON.stringify({ params: merged }) })
    },
    onSuccess: () => {
      setEdit({})
      void qc.invalidateQueries({ queryKey: ['bot', bot.id] })
      useToasts.getState().push('info', 'บันทึกเป็นเวอร์ชันใหม่แล้ว')
    },
    onError: (e) => useToasts.getState().push('error', errText(e)),
  })
  const editable = bot.status === 'DRAFT' || bot.status === 'PAUSED'
  return (
    <Card title="Config" subtitle={`${bot.config?.strategy.toUpperCase()} · version ${bot.config?.version} · ${bot.symbols.join(', ')}`}>
      {Object.keys(params).length === 0 && <InsetPanel className="text-secondary">ใช้ค่าเริ่มต้นตาม SPEC ทั้งหมด</InsetPanel>}
      <div className="grid gap-3 md:grid-cols-3">
        {Object.entries(params).map(([k, v]) => (
          <TextInput key={k} label={k} disabled={!editable} value={edit[k] ?? String(v)} onChange={(e) => setEdit({ ...edit, [k]: e.target.value })} />
        ))}
      </div>
      <p className="text-secondary text-[11px]">การแก้พารามิเตอร์สร้างเวอร์ชันใหม่ (ไม่แก้ทับ) และต้อง Pause บอทก่อน</p>
      <PrimaryButton className="self-start" disabled={!editable || Object.keys(edit).length === 0 || save.isPending} onClick={() => save.mutate()}>
        Save new version
      </PrimaryButton>
    </Card>
  )
}

function SignalDrawer({ s, onClose }: { s: Signal | null; onClose: () => void }) {
  return (
    <Drawer open={!!s} onOpenChange={(o) => !o && onClose()} title={s ? `${s.symbol.replace('USDT', '')} · ${s.strategy.toUpperCase()} · ${s.decision}` : ''}>
      {s && (
        <>
          <div className="grid grid-cols-3 gap-3">
            <StatTile label="S_tech" value={s.s_tech ? num(s.s_tech).toFixed(0) : '—'} />
            <StatTile label="S_ml" value={s.s_ml ? num(s.s_ml).toFixed(0) : '—'} />
            <StatTile label="S_ai" value={s.s_ai ? num(s.s_ai).toFixed(0) : '—'} />
            <StatTile label="Score" value={s.score ? num(s.score).toFixed(1) : '—'} />
            <StatTile label="Entry / Stop" value={`${fmtPrice(num(s.entry))} / ${fmtPrice(num(s.stop))}`} />
            <StatTile label="R:R" value={s.rr != null ? s.rr.toFixed(2) : '—'} />
          </div>
          <h3 className="text-[13px] font-semibold">Risk checks</h3>
          <ul className="flex flex-col gap-2">
            {s.checks.map((c) => (
              <li key={c.name} className="flex gap-2 text-[13px]">
                <span className={c.ok ? 'text-up' : 'text-down'} aria-label={c.ok ? 'passed' : 'failed'}>{c.ok ? '✓' : '✗'}</span>
                <span>
                  {c.name.replace(/_/g, ' ')}
                  {!c.ok && <span className="text-down block text-[11px]">{c.detail}</span>}
                </span>
              </li>
            ))}
          </ul>
          <p className="text-secondary text-[11px]">รายการนี้สรุปจากเหตุผลที่บันทึกไว้ (reject_reason) ไม่ใช่ log ของทุกข้อ</p>
        </>
      )}
    </Drawer>
  )
}

export default function BotDetail() {
  const { id = '' } = useParams()
  const bot = useBot(id)
  const perf = usePerformance(id)
  const trades = useBotTrades(id)
  const [filter, setFilter] = useState<'All' | 'Taken' | 'Skipped' | 'Rejected'>('All')
  const signals = useSignals(id, filter === 'All' ? undefined : filter.toUpperCase())
  const [open, setOpen] = useState<Signal | null>(null)

  if (bot.isPending) return <Skeleton className="h-64" />
  if (bot.isError || !bot.data) return <InsetPanel role="alert" className="text-down">ไม่พบบอทนี้ · <Link to="/bots" className="underline">กลับไปรายการ</Link></InsetPanel>
  const b = bot.data
  const p = perf.data
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <h1 className="text-[22px] leading-7 font-semibold">{b.name}</h1>
          <BotStatusPill status={STATUS_PILL(b.status)} label={`${b.status} · ${b.mode}`} />
        </div>
        <Controls id={id} status={b.status} />
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        <StatTile label="Net PnL" value={p ? <Signed value={num(p.net_pnl)} /> : '—'} />
        <StatTile label="Win rate" value={p ? `${(p.win_rate * 100).toFixed(0)}%` : '—'} />
        <StatTile label="Profit factor" value={p ? (p.profit_factor == null ? '—' : p.profit_factor.toFixed(2)) : '—'} />
        <StatTile label="Max DD" value={p ? `${(p.max_drawdown * 100).toFixed(1)}%` : '—'} />
        <StatTile label="Sharpe" value={p ? p.sharpe.toFixed(2) : '—'} />
      </div>

      <Card title="Equity curve & drawdown" subtitle="กำไรสะสมจากเทรดที่ปิดแล้ว">
        <CardState status={perf.isPending ? 'loading' : perf.isError ? 'error' : p && p.n_trades > 0 ? 'ready' : 'empty'} empty="ยังไม่มีเทรด — บอทยังไม่ได้เปิดสถานะ" onRetry={() => perf.refetch()} skeleton={<Skeleton className="h-52" />}>
          {p && (
            <>
              <LineChart series={[{ name: 'Equity', color: 'var(--accent)', data: p.equity as [number, number][], area: true }]} />
              <LineChart height={120} percent series={[{ name: 'Drawdown', color: 'var(--down)', data: p.drawdown.map(([t, v]) => [t, -v * 100] as [number, number]) }]} />
            </>
          )}
        </CardState>
      </Card>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <Card title="Signals" subtitle="รวมที่ข้าม/ถูกปฏิเสธ พร้อมเหตุผล" action={<Segmented label="Decision" options={['All', 'Taken', 'Skipped', 'Rejected'] as const} value={filter} onChange={setFilter} />}>
            <CardState status={signals.isPending ? 'loading' : signals.isError ? 'error' : signals.data?.length ? 'ready' : 'empty'} empty="ยังไม่มีสัญญาณ" onRetry={() => signals.refetch()}>
              <DataTable
                rowKey={(s) => s.id}
                onRowClick={setOpen}
                rows={signals.data ?? []}
                columns={[
                  { key: 't', header: 'Time', render: (s) => new Date(s.ts).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' }) },
                  { key: 'sym', header: 'Symbol', render: (s) => s.symbol.replace('USDT', '') },
                  { key: 'score', header: 'Score', render: (s) => (s.score ? num(s.score).toFixed(1) : '—') },
                  { key: 'dec', header: 'Decision', render: (s) => s.decision },
                  { key: 'why', header: 'Reason', render: (s) => s.reject_reason ?? '—' },
                ]}
              />
            </CardState>
          </Card>
        </div>
        <GatesCard id={id} status={b.status} />
      </div>

      <Card title="Trades" subtitle="รอบเทรดที่ปิดแล้ว">
        <CardState status={trades.isPending ? 'loading' : trades.isError ? 'error' : trades.data?.length ? 'ready' : 'empty'} empty="ยังไม่มีเทรด" onRetry={() => trades.refetch()}>
          <DataTable
            rowKey={(t) => t.id}
            rows={trades.data ?? []}
            columns={[
              { key: 'sym', header: 'Symbol', render: (t) => t.symbol.replace('USDT', '') },
              { key: 'closed', header: 'Closed', render: (t) => (t.closed_at ? new Date(t.closed_at).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' }) : '—') },
              { key: 'pnl', header: 'PnL', render: (t) => <Signed value={num(t.pnl_usdt)} /> },
              { key: 'r', header: 'R', render: (t) => <Signed value={num(t.pnl_r)} suffix="R" /> },
              { key: 'exit', header: 'Exit', render: (t) => t.exit_reason },
            ]}
          />
        </CardState>
      </Card>

      <ConfigCard bot={b} />
      <SignalDrawer s={open} onClose={() => setOpen(null)} />
    </div>
  )
}
