import { useQuery } from '@tanstack/react-query'
import { api, num, type Schemas } from '../../lib/api'
import { Card, InsetPanel, LineChart, StatTile, fmtPrice } from '../../ui'

export type Run = Schemas['BacktestOut']
type Metrics = {
  n_trades: number
  win_rate: number
  profit_factor: number | null
  expectancy_r: number
  net_pnl: number
  total_return: number
  max_drawdown: number
  sharpe: number
  worst_year_return: number
}
type Result = {
  walk_forward: boolean
  metrics: Metrics
  gate1: { passed: boolean; failures: string[] }
  monte_carlo: { max_dd_p95: number; max_dd_p50: number; final_return_p5: number; runs: number } | null
  folds: { symbol: string; test_start: string; test_end: string; params: Record<string, number>; is_pf: number | null; oos_pf: number | null; oos_trades: number; note: string }[]
  equity: [number, number][]
  buy_hold: [number, number][]
  warnings: string[]
  overfit_ratio: number | null
}

export const asResult = (r: Run): Result | null => (r.result as unknown as Result | null) ?? null
const pct = (v: number, d = 1) => `${(v * 100).toFixed(d)}%`
const pf = (v: number | null) => (v == null ? '∞' : v.toFixed(2))

/** Polls a job until it is DONE or FAILED. */
export function useJob(id: string | null) {
  return useQuery({
    queryKey: ['backtest', id],
    enabled: !!id,
    queryFn: () => api<Run>(`/backtests/${id}`),
    refetchInterval: (q) => (q.state.data && ['DONE', 'FAILED'].includes(q.state.data.status) ? false : 1500),
  })
}

export function JobStatus({ run }: { run: Run }) {
  if (run.status === 'FAILED')
    return (
      <InsetPanel role="alert" className="text-down">
        Backtest ล้มเหลว: {run.error}
      </InsetPanel>
    )
  if (run.status !== 'DONE') return <InsetPanel role="status">กำลังรัน backtest ({run.status})… อาจใช้เวลาหลายสิบวินาที</InsetPanel>
  return null
}

/** KPIs, gate 1 verdict, robustness and the equity curve of a finished run. */
export function ResultView({ run }: { run: Run }) {
  const r = asResult(run)
  if (!r) return <JobStatus run={run} />
  const m = r.metrics
  return (
    <div className="flex flex-col gap-4">
      <InsetPanel className={r.gate1.passed ? 'text-up font-semibold' : 'text-down font-semibold'}>
        {r.gate1.passed ? 'ผ่าน Gate 1 (out-of-sample)' : 'ไม่ผ่าน Gate 1'}
        {!r.gate1.passed && (
          <ul className="mt-1 list-disc pl-5 text-[13px] font-normal">
            {r.gate1.failures.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        )}
      </InsetPanel>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
        <StatTile label="Trades" value={m.n_trades} />
        <StatTile label="Win rate" value={pct(m.win_rate, 0)} />
        <StatTile label="Profit factor" value={pf(m.profit_factor)} />
        <StatTile label="Expectancy" value={`${m.expectancy_r >= 0 ? '+' : '−'}${Math.abs(m.expectancy_r).toFixed(2)}R`} />
        <StatTile label="Sharpe" value={m.sharpe.toFixed(2)} />
        <StatTile label="Max DD" value={pct(m.max_drawdown)} />
        <StatTile label="Worst year" value={pct(m.worst_year_return)} />
        <StatTile label="Net PnL" value={`${m.net_pnl >= 0 ? '+' : '−'}$${fmtPrice(Math.abs(m.net_pnl), 0)}`} />
      </div>
      {r.monte_carlo ? (
        <InsetPanel>
          Monte Carlo ({r.monte_carlo.runs} รอบ): Max DD p95 = <strong>{pct(r.monte_carlo.max_dd_p95)}</strong> (เกณฑ์ ≤ 20%), ผลตอบแทน p5 = {pct(r.monte_carlo.final_return_p5)}
        </InsetPanel>
      ) : (
        <InsetPanel className="text-secondary">Monte Carlo: เทรดน้อยเกินกว่าจะประเมิน (&lt; 10)</InsetPanel>
      )}
      {r.warnings.map((w) => (
        <InsetPanel key={w} role="alert" className="text-down text-[13px]">
          ⚠ {w}
        </InsetPanel>
      ))}
      {r.overfit_ratio != null && r.overfit_ratio > 1.5 && (
        <InsetPanel role="alert" className="text-down text-[13px]">
          ⚠ อาจ overfit: in-sample ดีกว่า out-of-sample {r.overfit_ratio.toFixed(1)} เท่า
        </InsetPanel>
      )}
      {r.equity.length > 1 && (
        <Card title="Equity vs buy & hold" subtitle="ช่วง out-of-sample, ทุนตั้งต้น $10,000">
          <LineChart
            series={[
              { name: 'Strategy', color: 'var(--accent)', data: r.equity, area: true },
              ...(r.buy_hold.length ? [{ name: 'Buy & hold', color: 'var(--text-secondary)', data: r.buy_hold }] : []),
            ]}
          />
        </Card>
      )}
    </div>
  )
}

export function Folds({ run }: { run: Run }) {
  const r = asResult(run)
  if (!r?.folds.length) return null
  return (
    <div className="shadow-inset rounded-panel overflow-x-auto p-4">
      <table className="w-full text-left text-[13px]">
        <thead>
          <tr className="text-secondary text-[11px]">
            {['Symbol', 'Test window', 'Params', 'In-sample PF', 'OOS PF', 'OOS trades'].map((h) => (
              <th key={h} className="pb-3 font-normal">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {r.folds.map((f) => (
            <tr key={`${f.symbol}-${f.test_start}`} className="border-secondary/15 border-t">
              <td className="py-2">{f.symbol.replace('USDT', '')}</td>
              <td>
                {f.test_start.slice(0, 10)} → {f.test_end.slice(0, 10)}
              </td>
              <td className="text-secondary">{Object.keys(f.params).length ? JSON.stringify(f.params) : 'default'}</td>
              <td>{pf(f.is_pf)}</td>
              <td className={num(f.oos_pf) >= 1 ? 'text-up' : 'text-down'}>{pf(f.oos_pf)}</td>
              <td>{f.oos_trades}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
