import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, ApiError, type Schemas } from '../../lib/api'
import { useStrategies } from '../bots/queries'
import { Card, CardState, DataTable, InsetPanel, PrimaryButton, Segmented, Slider, TextInput, cx, useToasts } from '../../ui'
import { Folds, JobStatus, ResultView, asResult, useJob } from './summary'

const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']

export default function BacktestLab() {
  const qc = useQueryClient()
  const strategies = useStrategies()
  const [strategy, setStrategy] = useState('s1')
  const [symbols, setSymbols] = useState<string[]>(['BTCUSDT'])
  const [years, setYears] = useState(3)
  const [fee, setFee] = useState('0.10')
  const [slip, setSlip] = useState('0.05')
  const [mode, setMode] = useState<'Walk-forward' | 'In-sample'>('Walk-forward')
  const [jobId, setJobId] = useState<string | null>(null)
  const job = useJob(jobId)
  const history = useQuery({ queryKey: ['backtests'], queryFn: () => api<Schemas['BacktestOut'][]>('/backtests'), refetchInterval: 10_000 })

  const wf = mode === 'Walk-forward'
  const run = useMutation({
    mutationFn: () =>
      api<Schemas['BacktestOut']>('/backtests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy, symbols: wf ? symbols : symbols.slice(0, 1), years, walk_forward: wf, fee: Number(fee) / 100, slippage: Number(slip) / 100 }),
      }),
    onSuccess: (r) => {
      setJobId(r.id)
      void qc.invalidateQueries({ queryKey: ['backtests'] })
    },
    onError: (e) => useToasts.getState().push('error', e instanceof ApiError ? e.message : 'เริ่ม backtest ไม่สำเร็จ'),
  })
  const preset = strategies.data?.find((s) => s.id === strategy)

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
      <Card title="Backtest Lab" subtitle="ค่าธรรมเนียมแบบ taker ทุกออเดอร์ + slippage ต่อด้าน" className="xl:col-span-1">
        <label className="flex flex-col gap-1">
          <span className="text-secondary text-[11px]">กลยุทธ์</span>
          <select className="shadow-inset rounded-control bg-transparent px-4 py-3" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
            {strategies.data?.map((s) => (
              <option key={s.id} value={s.id}>{s.id.toUpperCase()} · {s.name}</option>
            ))}
          </select>
        </label>
        {preset?.warning && <InsetPanel className="text-down text-[13px]">⚠ {preset.warning}</InsetPanel>}
        <fieldset className="flex flex-col gap-2">
          <legend className="text-secondary mb-1 text-[11px]">เหรียญ {wf ? '(รวมเป็นพอร์ตถ่วงน้ำหนักเท่ากัน)' : '(เหรียญเดียว)'}</legend>
          <div className="flex flex-wrap gap-3">
            {SYMBOLS.map((s) => (
              <button key={s} aria-pressed={symbols.includes(s)} onClick={() => setSymbols(symbols.includes(s) ? symbols.filter((x) => x !== s) : [...symbols, s])} className={cx('rounded-full px-4 py-1.5 text-[13px]', symbols.includes(s) ? 'shadow-pressed font-semibold' : 'shadow-raised-sm')}>
                {s.replace('USDT', '')}
              </button>
            ))}
          </div>
        </fieldset>
        <Slider label="ช่วงเวลา" value={years} min={1} max={5} step={0.5} unit=" ปี" onChange={setYears} hint="Gate 1 ต้องการข้อมูล ≥ 3 ปี" />
        <div className="grid grid-cols-2 gap-3">
          <TextInput label="Fee ต่อด้าน (%)" inputMode="decimal" value={fee} onChange={(e) => setFee(e.target.value)} />
          <TextInput label="Slippage ต่อด้าน (%)" inputMode="decimal" value={slip} onChange={(e) => setSlip(e.target.value)} />
        </div>
        <Segmented label="Mode" options={['Walk-forward', 'In-sample'] as const} value={mode} onChange={setMode} />
        {!wf && <p className="text-secondary text-[11px]">In-sample ใช้ดูภาพรวมเท่านั้น — ผ่าน Gate 1 ไม่ได้</p>}
        <PrimaryButton disabled={run.isPending || symbols.length === 0 || (job.data && !['DONE', 'FAILED'].includes(job.data.status))} onClick={() => run.mutate()}>
          Run backtest
        </PrimaryButton>
      </Card>

      <div className="flex flex-col gap-6 xl:col-span-2">
        <Card title="ผลลัพธ์" subtitle="ผลที่ใช้ตัดสินคือ out-of-sample รวมทุก fold">
          {!jobId && <InsetPanel className="text-secondary">เลือกกลยุทธ์แล้วกด Run backtest</InsetPanel>}
          {job.data && <JobStatus run={job.data} />}
          {job.data?.status === 'DONE' && <ResultView run={job.data} />}
        </Card>
        {job.data?.status === 'DONE' && asResult(job.data)?.folds.length ? (
          <Card title="Walk-forward folds" subtitle="train 12 เดือน → test 3 เดือน เลื่อนทีละ 3 เดือน">
            <Folds run={job.data} />
          </Card>
        ) : null}
        <Card title="ประวัติ" subtitle="รันล่าสุด">
          <CardState status={history.isPending ? 'loading' : history.isError ? 'error' : history.data?.length ? 'ready' : 'empty'} empty="ยังไม่เคยรัน" onRetry={() => history.refetch()}>
            <DataTable
              rowKey={(r) => r.id}
              onRowClick={(r) => setJobId(r.id)}
              rows={history.data ?? []}
              columns={[
                { key: 't', header: 'Time', render: (r) => new Date(r.created_at).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' }) },
                { key: 's', header: 'Strategy', render: (r) => String((r.request as { strategy?: string }).strategy ?? '').toUpperCase() },
                { key: 'sym', header: 'Symbols', render: (r) => ((r.request as { symbols?: string[] }).symbols ?? []).map((s) => s.replace('USDT', '')).join(', ') },
                { key: 'st', header: 'Status', render: (r) => r.status },
              ]}
            />
          </CardState>
        </Card>
      </div>
    </div>
  )
}
