import { useMemo, useState } from 'react'
import {
  AllocationBars, AssetRow, BotStatusPill, Card, CardState, ConfirmDialog, DataTable, Gauge, IconButton, InsetPanel, MarketStatusPill,
  NumberInput, PercentChips, PriceChart, PrimaryButton, Segmented, Signed, Skeleton, StatTile, StatusBadge, useToasts, type Candle,
} from '../../ui'
import { Plus } from 'lucide-react'

function demoCandles(): Candle[] {
  let p = 97000
  return Array.from({ length: 96 }, (_, i) => {
    const o = p
    p += Math.sin(i / 7) * 120 + ((i * 37) % 11) - 5
    return { time: 1_700_000_000 + i * 3600, open: o, high: Math.max(o, p) + 40, low: Math.min(o, p) - 40, close: p }
  })
}

export default function DevUi() {
  const [seg, setSeg] = useState<'1H' | '4H' | '1D'>('1D')
  const [pct, setPct] = useState(50)
  const [price, setPrice] = useState('97400.00')
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<'area' | 'candles'>('area')
  const push = useToasts((s) => s.push)
  const candles = useMemo(() => demoCandles(), [])
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Card title="Buttons & status" subtitle="PrimaryButton · IconButton · badges">
        <div className="flex flex-wrap items-center gap-4">
          <PrimaryButton>Buy BTC</PrimaryButton>
          <IconButton icon={<Plus size={16} />} label="Deposit" showLabel />
          <StatusBadge status="Open" /> <StatusBadge status="Filled" /> <StatusBadge status="Cancelled" />
          <MarketStatusPill /> <BotStatusPill status="RUNNING" label="3 bots running" /> <BotStatusPill status="PAUSED" /> <BotStatusPill status="KILLED" />
          <Signed value={2.84} suffix="%" /> <Signed value={-0.96} suffix="%" />
        </div>
      </Card>
      <Card title="Inputs" subtitle="Segmented · PercentChips · NumberInput">
        <Segmented label="Range" options={['1H', '4H', '1D'] as const} value={seg} onChange={setSeg} />
        <NumberInput label="Price" unit="USDT" value={price} onChange={setPrice} step={0.1} />
        <PercentChips value={pct} onChange={setPct} />
      </Card>
      <Card title="Tiles & rows" subtitle="StatTile · InsetPanel · AssetRow">
        <div className="grid grid-cols-2 gap-3">
          <StatTile label="24h high" value="98,120.00" />
          <StatTile label="24h low" value="94,305.40" />
        </div>
        <AssetRow symbol="BTC" name="Bitcoin" price={97412.5} change={2.84} spark={[1, 3, 2, 4, 5, 7]} />
        <AssetRow symbol="SOL" name="Solana" price={238.74} change={-0.96} spark={[7, 5, 6, 3, 2, 1]} />
        <InsetPanel>InsetPanel</InsetPanel>
      </Card>
      <Card title="Gauge & allocation">
        <Gauge value={68} label="Greed" />
        <AllocationBars items={[{ label: 'BTC', pct: 46 }, { label: 'ETH', pct: 24 }, { label: 'SOL', pct: 14 }, { label: 'Cash', pct: 16 }]} />
      </Card>
      <Card
        title="PriceChart"
        className="md:col-span-2"
        action={<Segmented label="Chart type" options={['area', 'candles'] as const} value={mode} onChange={setMode} />}
      >
        <PriceChart candles={candles} mode={mode} markers={[{ time: candles[30].time, side: 'buy', text: 'S1' }, { time: candles[60].time, side: 'sell' }]} />
      </Card>
      <Card title="DataTable & states" className="md:col-span-2">
        <DataTable
          rowKey={(r) => r.id}
          columns={[
            { key: 'pair', header: 'Pair', render: (r) => r.pair },
            { key: 'status', header: 'Status', render: (r) => <StatusBadge status={r.status} /> },
          ]}
          rows={[{ id: '1', pair: 'BTC/USDT', status: 'Filled' as const }, { id: '2', pair: 'SOL/USDT', status: 'Open' as const }]}
        />
        <div className="grid gap-3 md:grid-cols-3">
          <CardState status="loading"><span /></CardState>
          <CardState status="empty" empty="ยังไม่มีบอท — สร้างบอทแรกในโหมด Paper"><span /></CardState>
          <CardState status="error" onRetry={() => push('info', 'retry')}><span /></CardState>
        </div>
        <Skeleton className="h-10" />
        <div className="flex gap-3">
          <PrimaryButton onClick={() => push('risk', 'Daily loss breaker tripped')}>Toast</PrimaryButton>
          <PrimaryButton onClick={() => setOpen(true)}>ConfirmDialog (TOTP)</PrimaryButton>
        </div>
        <ConfirmDialog open={open} onOpenChange={setOpen} title="Reset kill switch" description="ต้องยืนยันด้วย TOTP" requireTotp onConfirm={() => push('info', 'confirmed')} />
      </Card>
    </div>
  )
}
