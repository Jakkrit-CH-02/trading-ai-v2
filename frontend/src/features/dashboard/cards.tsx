import { ArrowRightLeft, ArrowUpRight, Ellipsis, Minus, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { num, type Schemas } from '../../lib/api'
import { useRealtime } from '../../lib/realtime'
import {
  AllocationBars, AssetRow, BotStatusPill, Card, CardState, DataTable, Drawer, Gauge, IconButton, InsetPanel, PriceChart, PrimaryButton, Segmented,
  Signed, Skeleton, StatTile, StatusBadge, fmtCompact, fmtPrice, type Candle, type OrderStatus,
} from '../../ui'
import { cardStatus, useBots, useCandles, useOrders, useSentiment, useStats, useSummary, useWatchlist } from './queries'

const base = (s: string) => s.replace('USDT', '')
const NOT_CONNECTED = 'ยังไม่ได้เชื่อมบัญชี Demo — ใส่ BINANCE_API_KEY/SECRET ใน .env'

export function PortfolioCard() {
  const q = useSummary()
  const live = useRealtime((s) => s.portfolio)
  const d = live ?? q.data
  const status = q.isPending && !live ? 'loading' : q.isError && !live ? 'error' : !d?.connected ? 'empty' : 'ready'
  const [whole, cents] = d ? fmtPrice(num(d.equity)).split('.') : ['0', '00']
  return (
    <Card title="Portfolio balance" subtitle="Demo account · USD" action={<IconButton icon={<ArrowUpRight size={14} />} label="Open portfolio" className="size-9" />} className="h-full">
      <CardState status={status} empty={NOT_CONNECTED} onRetry={() => q.refetch()} skeleton={<Skeleton className="h-40" />}>
        {d && (
          <>
            <div>
              <div className="flex items-baseline gap-0.5 text-[40px] leading-[48px] font-bold">
                <span>${whole}</span>
                <span className="text-secondary text-2xl font-medium">.{cents}</span>
              </div>
              <div className="mt-2 flex items-center gap-2 text-[11px]">
                {d.pnl_today != null && (
                  <span className="shadow-inset rounded-full px-3 py-1 font-semibold">
                    <Signed value={num(d.pnl_today)} />
                  </span>
                )}
                {d.pnl_today_pct != null && (
                  <span className="text-secondary">
                    <Signed value={num(d.pnl_today_pct)} suffix="%" /> today
                  </span>
                )}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <StatTile label="Available" value={`$${fmtPrice(num(d.available))}`} />
              <StatTile label="In orders" value={`$${fmtPrice(num(d.in_orders))}`} />
            </div>
          </>
        )}
      </CardState>
      <div className="mt-auto flex justify-between pt-4">
        <IconButton icon={<Plus size={16} />} label="Deposit" showLabel disabled title="Not available on Demo" />
        <IconButton icon={<Minus size={16} />} label="Withdraw" showLabel disabled title="Not available on Demo" />
        <IconButton icon={<ArrowRightLeft size={16} />} label="Convert" showLabel disabled title="Not available on Demo" />
        <IconButton icon={<Ellipsis size={16} />} label="More" showLabel disabled />
      </div>
    </Card>
  )
}

const RANGES = { '1H': ['1h', 168], '4H': ['4h', 180], '1D': ['1d', 120] } as const
type Range = keyof typeof RANGES

export function PriceCard({ symbol }: { symbol: string }) {
  const [range, setRange] = useState<Range>('1D')
  const [interval, limit] = RANGES[range]
  const stats = useStats(symbol)
  const candles = useCandles(symbol, interval, limit)
  const tick = useRealtime((s) => s.tickers[symbol])
  const last = tick ? num(tick.last) : stats.data ? num(stats.data.last) : NaN
  const change = tick ? num(tick.change24h_pct) : stats.data ? num(stats.data.change24h_pct) : NaN
  const data: Candle[] = useMemo(() => (candles.data ?? []).map((c) => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close })), [candles.data])
  const st = stats.data
  return (
    <Card
      title={
        <span className="flex items-center gap-3">
          <span className="bg-ink text-on-ink grid size-9 place-items-center rounded-full text-[13px]">{symbol[0]}</span>
          <span className="flex items-baseline gap-3">
            <span>
              {base(symbol)} / USDT
              <span className="text-secondary block text-[11px] font-normal">Spot</span>
            </span>
            {!Number.isNaN(last) && <span className="text-[22px] leading-7 font-semibold">{fmtPrice(last)}</span>}
            {!Number.isNaN(change) && (
              <span className="text-[11px]">
                <Signed value={change} suffix="%" /> · 24h
              </span>
            )}
          </span>
        </span>
      }
      action={<Segmented label="Range" options={['1H', '4H', '1D'] as const} value={range} onChange={setRange} />}
    >
      <CardState status={cardStatus(candles, (d: unknown[]) => d.length === 0)} empty="ยังไม่มีข้อมูลกราฟ — รัน softtrade backfill" onRetry={() => candles.refetch()} skeleton={<Skeleton className="h-[260px]" />}>
        <PriceChart candles={data} />
      </CardState>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatTile label="24h high" value={st ? fmtPrice(num(st.high)) : '—'} />
        <StatTile label="24h low" value={st ? fmtPrice(num(st.low)) : '—'} />
        <StatTile label="24h volume" value={st ? `${fmtCompact(num(st.volume))} ${base(symbol)}` : '—'} />
        <StatTile label="Funding" value={st?.funding_rate != null ? `${num(st.funding_rate).toFixed(4)}%` : '—'} />
      </div>
    </Card>
  )
}

export function WatchlistCard({ selected, onSelect }: { selected: string; onSelect: (s: string) => void }) {
  const q = useWatchlist()
  const ticks = useRealtime((s) => s.tickers)
  return (
    <Card title="Watchlist" subtitle={`${q.data?.length ?? 0} markets · 24h change`} className="h-full">
      <CardState status={cardStatus(q, (d: unknown[]) => d.length === 0)} empty="ยังไม่มีเหรียญในรายการ" onRetry={() => q.refetch()} skeleton={<Skeleton className="h-64" />}>
        <div className="flex flex-col gap-3">
          {q.data?.map((w) => {
            const t = ticks[w.symbol]
            return (
              <AssetRow
                key={w.symbol}
                symbol={base(w.symbol)}
                name={w.name}
                price={num(t?.last ?? w.last)}
                change={num(t?.change24h_pct ?? w.change24h_pct)}
                spark={w.spark}
                selected={w.symbol === selected}
                onClick={() => onSelect(w.symbol)}
              />
            )
          })}
        </div>
      </CardState>
    </Card>
  )
}

export function BotsCard({ symbol }: { symbol: string }) {
  const q = useBots()
  const risk = useRealtime((s) => s.risk)
  const nav = useNavigate()
  const d = q.data
  return (
    <Card title="Bots & AI insight" subtitle="สรุปบอทและมุมมอง AI" className="h-full">
      <CardState status={cardStatus(q)} onRetry={() => q.refetch()}>
        {d && (
          <>
            <div className="flex items-center gap-3">
              <BotStatusPill status={risk?.kill_switch ? 'KILLED' : 'RUNNING'} label={risk?.kill_switch ? 'KILL SWITCH' : `${d.running} bots running`} />
              <span className="text-secondary text-[11px]">
                Open risk {num(d.open_risk_pct).toFixed(2)}% / {num(d.open_risk_cap_pct).toFixed(0)}%
              </span>
            </div>
            {d.bots.length === 0 && <InsetPanel className="text-secondary">ยังไม่มีบอท — สร้างบอทแรกในโหมด Paper</InsetPanel>}
          </>
        )}
      </CardState>
      <InsetPanel className="text-secondary flex flex-col gap-2">
        <span className="text-primary text-[13px] font-semibold">{base(symbol)} · AI brief</span>
        ยังไม่เปิดใช้งาน AI Analyst — มาใน Phase ถัดไป
      </InsetPanel>
      <PrimaryButton className="mt-auto" onClick={() => nav('/bots')}>
        Open bot
      </PrimaryButton>
    </Card>
  )
}

export function SentimentCard() {
  const q = useSentiment()
  return (
    <Card title="Market sentiment" subtitle="Fear & Greed index" action={<span className="shadow-inset rounded-full px-3 py-1 text-[11px]">Daily</span>}>
      <CardState status={cardStatus(q)} onRetry={() => q.refetch()} skeleton={<Skeleton className="h-28" />}>
        {q.data && (
          <>
            <Gauge value={q.data.value} label={q.data.label} />
            <div className="text-secondary flex justify-between text-[11px]">
              <span>Extreme fear</span>
              <span>Extreme greed</span>
            </div>
          </>
        )}
      </CardState>
    </Card>
  )
}

export function AllocationCard() {
  const q = useSummary()
  const live = useRealtime((s) => s.portfolio)
  const d = live ?? q.data
  const status = q.isPending && !live ? 'loading' : q.isError && !live ? 'error' : !d?.connected || d.allocation.length === 0 ? 'empty' : 'ready'
  return (
    <Card title="Allocation" subtitle="Share of portfolio">
      <CardState status={status} empty="ยังไม่มีสินทรัพย์ในพอร์ต" onRetry={() => q.refetch()} skeleton={<Skeleton className="h-28" />}>
        {d && <AllocationBars items={d.allocation} />}
      </CardState>
    </Card>
  )
}

const UI_STATUS: Record<string, OrderStatus> = { FILLED: 'Filled', NEW: 'Open', PARTIALLY_FILLED: 'Open', CANCELED: 'Cancelled', EXPIRED: 'Cancelled', REJECTED: 'Cancelled' }

export function RecentOrders() {
  const [tab, setTab] = useState<'All' | 'Open' | 'Filled'>('All')
  const q = useOrders(tab.toLowerCase() as 'all' | 'open' | 'filled')
  const [open, setOpen] = useState<Schemas['OrderOut'] | null>(null)
  return (
    <>
      <Card title="Recent orders" subtitle="Open orders from the Demo exchange" action={<Segmented label="Filter" options={['All', 'Open', 'Filled'] as const} value={tab} onChange={setTab} />}>
        <CardState status={cardStatus(q, (d: unknown[]) => d.length === 0)} empty="ยังไม่มีออเดอร์" onRetry={() => q.refetch()} skeleton={<Skeleton className="h-40" />}>
          <DataTable
            rowKey={(o) => o.id}
            onRowClick={setOpen}
            rows={q.data ?? []}
            columns={[
              { key: 'pair', header: 'Pair', render: (o) => <strong>{base(o.symbol)}/USDT</strong> },
              { key: 'side', header: 'Side', render: (o) => <span className={o.side === 'BUY' ? 'text-up' : 'text-down'}>{o.side === 'BUY' ? 'Buy' : 'Sell'}</span> },
              { key: 'type', header: 'Type', render: (o) => o.type.replace('_', ' ').toLowerCase() },
              { key: 'price', header: 'Price', render: (o) => (o.price ? fmtPrice(num(o.price)) : 'Market') },
              { key: 'amount', header: 'Amount', render: (o) => num(o.qty) },
              { key: 'source', header: 'Source', render: (o) => o.source ?? '—' },
              { key: 'status', header: 'Status', render: (o) => <StatusBadge status={UI_STATUS[o.status] ?? 'Open'} /> },
              { key: 'time', header: 'Time', render: (o) => (o.ts ? new Date(o.ts).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : '—') },
            ]}
          />
        </CardState>
      </Card>
      <Drawer open={open != null} onOpenChange={(o) => !o && setOpen(null)} title={open ? `${base(open.symbol)}/USDT · ${open.side}` : ''}>
        {open && (
          <dl className="grid grid-cols-2 gap-3">
            {Object.entries({ ID: open.id, Type: open.type, Status: open.status, Price: open.price ?? 'Market', Amount: open.qty, Filled: open.executed_qty }).map(([k, v]) => (
              <StatTile key={k} label={k} value={<span className="break-all">{String(v)}</span>} />
            ))}
          </dl>
        )}
      </Drawer>
    </>
  )
}

