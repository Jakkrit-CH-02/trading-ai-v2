import { Plus } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { num } from '../../lib/api'
import { BotStatusPill, Card, CardState, InsetPanel, LineChart, PrimaryButton, Signed, Skeleton } from '../../ui'
import { STATUS_PILL, useBotList, usePerformance, type Bot } from './queries'

function BotCard({ bot }: { bot: Bot }) {
  const nav = useNavigate()
  const perf = usePerformance(bot.id)
  const p = perf.data
  return (
    <div
      role="link"
      tabIndex={0}
      onClick={() => nav(`/bots/${bot.id}`)}
      onKeyDown={(e) => e.key === 'Enter' && nav(`/bots/${bot.id}`)}
      className="cursor-pointer text-left"
      aria-label={`Open ${bot.name}`}
    >
      <Card
        title={bot.name}
        subtitle={`${bot.config?.strategy.toUpperCase() ?? '?'} · ${bot.symbols.map((s) => s.replace('USDT', '')).join(', ')} · ${bot.mode}`}
        action={<BotStatusPill status={STATUS_PILL(bot.status)} label={bot.status} />}
        className="h-full"
      >
        <div className="flex items-baseline justify-between">
          <span className="text-secondary text-[11px]">Net PnL</span>
          <span className="text-[22px] leading-7 font-semibold">{p ? <Signed value={num(p.net_pnl)} /> : '—'}</span>
        </div>
        {p && p.equity.length > 1 ? <LineChart height={80} series={[{ name: '', color: 'var(--accent)', data: p.equity as [number, number][], area: true }]} /> : <InsetPanel className="text-secondary text-[13px]">ยังไม่มีเทรด</InsetPanel>}
      </Card>
    </div>
  )
}

export default function Bots() {
  const nav = useNavigate()
  const q = useBotList()
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] leading-7 font-semibold">Bots</h1>
        <PrimaryButton onClick={() => nav('/bots/new')} className="flex items-center gap-2">
          <Plus size={16} /> New bot
        </PrimaryButton>
      </div>
      <CardState status={q.isPending ? 'loading' : q.isError ? 'error' : q.data?.length ? 'ready' : 'empty'} empty="ยังไม่มีบอท — สร้างบอทแรกในโหมด Paper" onRetry={() => q.refetch()} skeleton={<Skeleton className="h-48" />}>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
          {q.data?.map((b) => (
            <BotCard key={b.id} bot={b} />
          ))}
        </div>
      </CardState>
    </div>
  )
}
