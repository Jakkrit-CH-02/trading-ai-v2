import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api, ApiError, num, type Schemas } from '../../lib/api'
import { useRealtime, useRealtimeConnection } from '../../lib/realtime'
import { useCandles, useOrders, useStats } from '../dashboard/queries'
import {
  Card, CardState, DataTable, InsetPanel, NumberInput, PriceChart, PrimaryButton, Segmented, Signed, Skeleton, StatTile, fmtPrice, useToasts, type Candle,
} from '../../ui'

const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']
const RANGES = { '1H': ['1h', 168], '4H': ['4h', 180], '1D': ['1d', 120] } as const
const JSON_HEADERS = { 'Content-Type': 'application/json' }
const base = (s: string) => s.replace('USDT', '')

type Preview = Schemas['PreviewOut']

function OrderBook({ symbol }: { symbol: string }) {
  const q = useQuery({ queryKey: ['depth', symbol], queryFn: () => api<Schemas['Depth']>(`/markets/${symbol}/depth?limit=8`), refetchInterval: 3000 })
  const asks = [...(q.data?.asks ?? [])].reverse()
  const row = (side: 'ask' | 'bid') => (l: Schemas['DepthLevel']) => (
    <div key={`${side}${l.price}`} className="flex justify-between text-[13px]">
      <span className={side === 'ask' ? 'text-down' : 'text-up'}>{fmtPrice(num(l.price))}</span>
      <span className="text-secondary">{num(l.qty).toFixed(4)}</span>
    </div>
  )
  return (
    <Card title="Order book" subtitle={`${base(symbol)}/USDT · 8 ระดับ`}>
      <CardState status={q.isPending ? 'loading' : q.isError ? 'error' : 'ready'} onRetry={() => q.refetch()} skeleton={<Skeleton className="h-48" />}>
        <InsetPanel className="flex flex-col gap-1">
          {asks.map(row('ask'))}
          <hr className="border-secondary/20 my-1" />
          {q.data?.bids.map(row('bid'))}
        </InsetPanel>
      </CardState>
    </Card>
  )
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

function PlaceOrder({ symbol, last }: { symbol: string; last: number }) {
  const qc = useQueryClient()
  const [type, setType] = useState<'Limit' | 'Market'>('Limit')
  const [entry, setEntry] = useState('')
  const [stop, setStop] = useState('')
  const [tp1, setTp1] = useState('')
  const isLimit = type === 'Limit'
  const body = useMemo(
    () => JSON.stringify({ symbol, order_type: type.toUpperCase(), entry: isLimit && entry ? entry : null, stop: stop || '0', tp1: tp1 || null }),
    [symbol, type, entry, stop, tp1, isLimit],
  )
  const ready = Number(stop) > 0 && (!isLimit || Number(entry) > 0)
  const settled = useDebounced(body, 400)

  // live "risk of this order" while the user types: the Risk Engine is the only judge
  const pq = useQuery({
    queryKey: ['order-preview', settled],
    enabled: ready && settled === body,
    retry: false,
    queryFn: () => api<Preview>('/orders/preview', { method: 'POST', headers: JSON_HEADERS, body: settled }),
  })
  const preview = ready && settled === body ? pq.data : undefined
  const err = ready && pq.error ? (pq.error instanceof ApiError ? pq.error.message : 'ประเมินความเสี่ยงไม่ได้') : null

  const place = useMutation({
    mutationFn: () => api<Schemas['OrderResult']>('/orders', { method: 'POST', headers: JSON_HEADERS, body }),
    onSuccess: (r) => {
      useToasts.getState().push(r.status === 'PROTECTED' || r.status === 'NEW' ? 'info' : 'error', `${r.status}: ${r.detail || 'ok'}`)
      void qc.invalidateQueries({ queryKey: ['orders'] })
      void qc.invalidateQueries({ queryKey: ['summary'] })
    },
    onError: (e) => useToasts.getState().push('error', e instanceof ApiError ? e.message : 'ส่งออเดอร์ไม่สำเร็จ'),
  })

  return (
    <Card title="Place order" subtitle={`${base(symbol)} / USDT · Spot long · ขนาดคำนวณจากความเสี่ยง ไม่ต้องกรอก`}>
      <div className="grid grid-cols-2 gap-2" role="group" aria-label="Side">
        <button aria-pressed className="bg-surface shadow-pressed rounded-full py-2 font-semibold">Buy</button>
        <button disabled title="Spot ปิดสถานะด้วย stop/TP ที่วางไว้ — ยังไม่รองรับ Sell เอง" className="bg-surface text-secondary rounded-full py-2 opacity-60">Sell</button>
      </div>
      <Segmented label="Order type" options={['Limit', 'Market'] as const} value={type} onChange={setType} />
      {isLimit ? <NumberInput label="Entry price" unit="USDT" value={entry} onChange={setEntry} step={0.01} /> : <InsetPanel className="text-secondary text-[13px]">Market: ราคาอ้างอิง {fmtPrice(last)} — ต้องมี order book พอรับ slippage ≤ 30 bps</InsetPanel>}
      <NumberInput label="Stop-loss (บังคับ)" unit="USDT" value={stop} onChange={setStop} step={0.01} />
      <NumberInput label="Take profit (R:R ≥ 1.5)" unit="USDT" value={tp1} onChange={setTp1} step={0.01} />

      {err && <InsetPanel role="alert" className="text-down text-[13px]">{err}</InsetPanel>}
      {preview && (
        <InsetPanel className="flex flex-col gap-2" aria-live="polite">
          <div className="flex items-baseline justify-between">
            <span className="text-secondary text-[11px]">ความเสี่ยงของออเดอร์นี้</span>
            <span className="text-[22px] leading-7 font-semibold">{num(preview.risk_pct_of_equity).toFixed(2)}% <span className="text-secondary text-[11px] font-normal">ของพอร์ต</span></span>
          </div>
          <div className="text-[13px]">
            ขนาด {num(preview.qty)} {base(symbol)} · มูลค่า ${fmtPrice(num(preview.notional))} · เสี่ยง ${fmtPrice(num(preview.risk_amount))}
          </div>
          {!preview.approved && (
            <ul role="alert" className="text-down text-[13px]">
              {preview.checks.filter((c) => !c.passed).map((c) => (
                <li key={c.name}>✗ {c.name}: {c.detail}</li>
              ))}
            </ul>
          )}
          {preview.adjustments.map((a) => <span key={a} className="text-secondary text-[11px]">• {a}</span>)}
        </InsetPanel>
      )}
      <PrimaryButton disabled={!preview?.approved || place.isPending} onClick={() => place.mutate()}>
        Buy {base(symbol)}
      </PrimaryButton>
    </Card>
  )
}

function OpenOrders() {
  const qc = useQueryClient()
  const q = useOrders('open')
  const cancel = useMutation({
    mutationFn: (o: Schemas['OrderOut']) => api(`/orders/${encodeURIComponent(o.id)}?symbol=${o.symbol}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['orders'] }),
    onError: (e) => useToasts.getState().push('error', e instanceof ApiError ? e.message : 'ยกเลิกไม่สำเร็จ'),
  })
  return (
    <Card title="Open orders" subtitle="ออเดอร์ที่ยังค้างอยู่บน Demo exchange" className="xl:col-span-3">
      <CardState status={q.isPending ? 'loading' : q.isError ? 'error' : q.data?.length ? 'ready' : 'empty'} empty="ไม่มีออเดอร์ค้าง" onRetry={() => q.refetch()} skeleton={<Skeleton className="h-24" />}>
        <DataTable
          rowKey={(o) => o.id}
          rows={q.data ?? []}
          columns={[
            { key: 'pair', header: 'Pair', render: (o) => <strong>{base(o.symbol)}/USDT</strong> },
            { key: 'side', header: 'Side', render: (o) => <span className={o.side === 'BUY' ? 'text-up' : 'text-down'}>{o.side === 'BUY' ? 'Buy' : 'Sell'}</span> },
            { key: 'type', header: 'Type', render: (o) => o.type.replace('_', ' ').toLowerCase() },
            { key: 'price', header: 'Price', render: (o) => (o.price ? fmtPrice(num(o.price)) : '—') },
            { key: 'qty', header: 'Amount', render: (o) => `${num(o.executed_qty)} / ${num(o.qty)}` },
            { key: 'x', header: '', render: (o) => <button className="bg-surface shadow-raised-sm rounded-full px-3 py-1 text-[11px]" onClick={() => cancel.mutate(o)}>Cancel</button> },
          ]}
        />
      </CardState>
    </Card>
  )
}

function OrderHistory() {
  const q = useOrders('history')
  return (
    <Card title="Order history" subtitle="ทุกออเดอร์ที่ระบบส่ง (รวม stop / take-profit) ล่าสุดก่อน เก็บใน DB" className="xl:col-span-3">
      <CardState status={q.isPending ? 'loading' : q.isError ? 'error' : q.data?.length ? 'ready' : 'empty'} empty="ยังไม่เคยส่งออเดอร์" onRetry={() => q.refetch()} skeleton={<Skeleton className="h-24" />}>
        <DataTable
          rowKey={(o) => o.id}
          rows={q.data ?? []}
          columns={[
            { key: 'ts', header: 'Time', render: (o) => (o.ts ? new Date(o.ts).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' }) : '—') },
            { key: 'pair', header: 'Pair', render: (o) => <strong>{base(o.symbol)}/USDT</strong> },
            { key: 'side', header: 'Side', render: (o) => <span className={o.side === 'BUY' ? 'text-up' : 'text-down'}>{o.side === 'BUY' ? 'Buy' : 'Sell'}</span> },
            { key: 'type', header: 'Type', render: (o) => o.type.replace(/_/g, ' ').toLowerCase() },
            { key: 'price', header: 'Price', render: (o) => (o.price ? fmtPrice(num(o.price)) : '—') },
            { key: 'qty', header: 'Filled / Amount', render: (o) => `${num(o.executed_qty)} / ${num(o.qty)}` },
            { key: 'status', header: 'Status', render: (o) => o.status.replace(/_/g, ' ').toLowerCase() },
            { key: 'src', header: 'Source', render: (o) => o.source ?? '—' },
          ]}
        />
      </CardState>
    </Card>
  )
}

export default function Trade() {
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [range, setRange] = useState<keyof typeof RANGES>('1H')
  const [mode, setMode] = useState<'candles' | 'area'>('candles')
  useRealtimeConnection(SYMBOLS.map((s) => `ticker:${s}`))
  const [interval, limit] = RANGES[range]
  const candles = useCandles(symbol, interval, limit)
  const stats = useStats(symbol)
  const tick = useRealtime((s) => s.tickers[symbol])
  const last = num(tick?.last ?? stats.data?.last)
  const change = num(tick?.change24h_pct ?? stats.data?.change24h_pct)
  const data: Candle[] = useMemo(() => (candles.data ?? []).map((c) => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close })), [candles.data])

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
      <div className="flex flex-col gap-6 xl:col-span-2">
        <Card
          title={
            <span className="flex flex-wrap items-baseline gap-3">
              <select aria-label="Symbol" className="shadow-inset rounded-full bg-transparent px-3 py-1" value={symbol} onChange={(e) => setSymbol(e.target.value)}>
                {SYMBOLS.map((s) => <option key={s} value={s}>{base(s)} / USDT</option>)}
              </select>
              {!Number.isNaN(last) && <span className="text-[22px] leading-7 font-semibold">{fmtPrice(last)}</span>}
              {!Number.isNaN(change) && <span className="text-[11px]"><Signed value={change} suffix="%" /> · 24h</span>}
            </span>
          }
          action={
            <span className="flex gap-3">
              <Segmented label="Chart type" options={['candles', 'area'] as const} value={mode} onChange={setMode} />
              <Segmented label="Range" options={['1H', '4H', '1D'] as const} value={range} onChange={setRange} />
            </span>
          }
        >
          <CardState status={candles.isPending ? 'loading' : candles.isError ? 'error' : data.length ? 'ready' : 'empty'} empty="ยังไม่มีข้อมูลกราฟ — รัน softtrade backfill" onRetry={() => candles.refetch()} skeleton={<Skeleton className="h-[380px]" />}>
            <PriceChart candles={data} mode={mode} height={380} />
          </CardState>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatTile label="24h high" value={stats.data ? fmtPrice(num(stats.data.high)) : '—'} />
            <StatTile label="24h low" value={stats.data ? fmtPrice(num(stats.data.low)) : '—'} />
            <StatTile label="24h volume" value={stats.data ? num(stats.data.volume).toFixed(0) : '—'} />
            <StatTile label="Marker บอท" value="ยังไม่มีบอทเทรด" />
          </div>
        </Card>
      </div>
      <div className="flex flex-col gap-6">
        <PlaceOrder symbol={symbol} last={last} />
        <OrderBook symbol={symbol} />
      </div>
      <OpenOrders />
      <OrderHistory />
    </div>
  )
}
