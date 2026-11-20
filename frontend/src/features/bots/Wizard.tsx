import { useMutation, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError, num, type Schemas } from '../../lib/api'
import { Card, CardState, InsetPanel, PrimaryButton, Skeleton, StatTile, TextInput, cx, useToasts } from '../../ui'
import { Folds, JobStatus, ResultView, asResult, useJob } from '../backtest/summary'
import { useAccounts, useStrategies } from './queries'

const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']
const STEPS = ['ตลาด & เหรียญ', 'กลยุทธ์', 'Risk profile', 'Backtest']
const JSON_HEADERS = { 'Content-Type': 'application/json' }

function Stepper({ step }: { step: number }) {
  return (
    <ol className="flex flex-wrap gap-3" aria-label="Steps">
      {STEPS.map((s, i) => (
        <li key={s} aria-current={i === step ? 'step' : undefined} className={cx('rounded-full px-4 py-1.5 text-[13px]', i === step ? 'shadow-pressed font-semibold' : 'shadow-raised-sm text-secondary')}>
          {i + 1}. {s}
        </li>
      ))}
    </ol>
  )
}

export default function Wizard() {
  const nav = useNavigate()
  const [step, setStep] = useState(0)
  const [name, setName] = useState('')
  const [accountId, setAccountId] = useState('')
  const [symbols, setSymbols] = useState<string[]>(['BTCUSDT'])
  const [strategy, setStrategy] = useState('s1')
  const [params, setParams] = useState<Record<string, number>>({})
  const [jobId, setJobId] = useState<string | null>(null)
  const [accepted, setAccepted] = useState(false)

  const accounts = useAccounts()
  const strategies = useStrategies()
  const profile = useQuery({ queryKey: ['risk-profile'], queryFn: () => api<Schemas['RiskProfileOut-Output']>('/risk/profile') })
  const job = useJob(jobId)
  const preset = strategies.data?.find((s) => s.id === strategy)
  // only parameters the user actually changed are sent: defaults stay defaults
  const changed = useMemo(() => Object.fromEntries(Object.entries(params).filter(([k, v]) => preset && preset.params[k] !== v)), [params, preset])

  const run = useMutation({
    mutationFn: () => api<Schemas['BacktestOut']>('/backtests', { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ strategy, symbols, params: changed, years: 3, walk_forward: true }) }),
    onSuccess: (r) => setJobId(r.id),
    onError: (e) => useToasts.getState().push('error', e instanceof ApiError ? e.message : 'เริ่ม backtest ไม่สำเร็จ'),
  })
  const create = useMutation({
    mutationFn: async () => {
      const bot = await api<Schemas['BotDetail']>('/bots', { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ name, account_id: accountId, symbols, strategy, params: changed }) })
      try {
        await api(`/bots/${bot.id}/start`, { method: 'POST' })
      } catch (e) {
        useToasts.getState().push('error', `สร้างบอทแล้วแต่ยังไม่เริ่ม: ${e instanceof ApiError ? e.message : ''}`)
      }
      return bot
    },
    onSuccess: (b) => nav(`/bots/${b.id}`),
    onError: (e) => useToasts.getState().push('error', e instanceof ApiError ? e.message : 'สร้างบอทไม่สำเร็จ'),
  })

  const result = job.data ? asResult(job.data) : null
  const gatePassed = result?.gate1.passed ?? false
  const step1Ok = name.trim().length > 0 && !!accountId && symbols.length > 0
  const canCreate = job.data?.status === 'DONE' && (gatePassed || accepted)

  return (
    <div className="mx-auto flex max-w-[960px] flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] leading-7 font-semibold">New bot</h1>
        <Link to="/bots" className="text-secondary text-[13px] underline">
          ยกเลิก
        </Link>
      </div>
      <Stepper step={step} />

      {step === 0 && (
        <Card title="ตลาด & เหรียญ" subtitle="Spot (Futures ยังไม่เปิดใช้)">
          <TextInput label="ชื่อบอท" value={name} onChange={(e) => setName(e.target.value)} maxLength={64} />
          <CardState status={accounts.isPending ? 'loading' : accounts.isError ? 'error' : accounts.data?.length ? 'ready' : 'empty'} empty={<span>ยังไม่มีบัญชี — <Link className="underline" to="/settings">เพิ่ม API key ของ Binance Demo</Link> ก่อน</span>} onRetry={() => accounts.refetch()}>
            <label className="flex flex-col gap-1">
              <span className="text-secondary text-[11px]">บัญชี</span>
              <select className="shadow-inset rounded-control bg-transparent px-4 py-3" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                <option value="">เลือกบัญชี…</option>
                {accounts.data?.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label} (…{a.api_key_last4}){a.permissions_checked_at ? '' : ' · ยังไม่ผ่านการตรวจ'}
                  </option>
                ))}
              </select>
            </label>
          </CardState>
          <fieldset className="flex flex-col gap-2">
            <legend className="text-secondary mb-1 text-[11px]">เหรียญ</legend>
            <div className="flex flex-wrap gap-3">
              {SYMBOLS.map((s) => (
                <button key={s} aria-pressed={symbols.includes(s)} onClick={() => setSymbols(symbols.includes(s) ? symbols.filter((x) => x !== s) : [...symbols, s])} className={cx('rounded-full px-4 py-1.5 text-[13px]', symbols.includes(s) ? 'shadow-pressed font-semibold' : 'shadow-raised-sm')}>
                  {s.replace('USDT', '')}
                </button>
              ))}
            </div>
          </fieldset>
        </Card>
      )}

      {step === 1 && (
        <Card title="กลยุทธ์" subtitle="เลือก preset แล้วปรับพารามิเตอร์ได้ (ค่าเริ่มต้นคือค่าตาม SPEC)">
          <CardState status={strategies.isPending ? 'loading' : strategies.isError ? 'error' : 'ready'} onRetry={() => strategies.refetch()} skeleton={<Skeleton className="h-40" />}>
            <div className="grid gap-3 md:grid-cols-2">
              {strategies.data?.map((s) => (
                <button key={s.id} aria-pressed={s.id === strategy} onClick={() => { setStrategy(s.id); setParams({}) }} className={cx('rounded-panel p-4 text-left', s.id === strategy ? 'shadow-pressed' : 'shadow-raised-sm')}>
                  <strong>{s.id.toUpperCase()} · {s.name}</strong>
                  <span className="text-secondary block text-[13px]">{s.description}</span>
                  {s.warning && <span className="text-down mt-1 block text-[11px]">⚠ {s.warning}</span>}
                </button>
              ))}
            </div>
            {preset && (
              <details className="mt-2">
                <summary className="cursor-pointer text-[13px] font-semibold">พารามิเตอร์ ({Object.keys(preset.params).length})</summary>
                <div className="mt-3 grid gap-3 md:grid-cols-3">
                  {Object.entries(preset.params).map(([k, def]) => (
                    <TextInput key={k} label={`${k} (default ${def})`} inputMode="decimal" value={String(params[k] ?? def)} onChange={(e) => { const v = Number(e.target.value); if (!Number.isNaN(v)) setParams({ ...params, [k]: v }) }} />
                  ))}
                </div>
              </details>
            )}
          </CardState>
        </Card>
      )}

      {step === 2 && (
        <Card title="Risk profile" subtitle="ใช้โปรไฟล์ร่วมของระบบ แก้ได้ที่ Risk & Settings (ต้อง 2FA)">
          <CardState status={profile.isPending ? 'loading' : profile.isError ? 'error' : 'ready'} onRetry={() => profile.refetch()} skeleton={<Skeleton className="h-32" />}>
            {profile.data && (
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <StatTile label="Risk per trade" value={`${(num(profile.data.risk_per_trade) * 100).toFixed(2)}%`} />
                <StatTile label="Max positions" value={profile.data.max_positions} />
                <StatTile label="Daily loss limit" value={`${(num(profile.data.daily_loss) * 100).toFixed(2)}%`} />
                <StatTile label="Max drawdown (kill)" value={`${(num(profile.data.max_drawdown) * 100).toFixed(0)}%`} />
              </div>
            )}
          </CardState>
          <Link to="/settings" className="text-secondary text-[13px] underline">เปิด Risk & Settings</Link>
        </Card>
      )}

      {step === 3 && (
        <Card title="Backtest" subtitle="Walk-forward 3 ปี, ผล out-of-sample เท่านั้น — ก่อนเริ่ม Paper">
          {!jobId && (
            <PrimaryButton onClick={() => run.mutate()} disabled={run.isPending} className="self-start">
              Run backtest
            </PrimaryButton>
          )}
          {job.data && <JobStatus run={job.data} />}
          {job.data?.status === 'DONE' && (
            <>
              <ResultView run={job.data} />
              <Folds run={job.data} />
            </>
          )}
          {job.data?.status === 'DONE' && !gatePassed && (
            <label className="flex items-start gap-3 text-[13px]">
              <input type="checkbox" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} className="mt-1" />
              <span>เข้าใจว่า backtest นี้ไม่ผ่าน Gate 1 — เริ่มได้เฉพาะโหมด Paper (Demo) และจะ Go live ไม่ได้จนกว่าจะผ่านเกณฑ์</span>
            </label>
          )}
          {job.data?.status === 'FAILED' && (
            <button className="bg-surface shadow-raised-sm self-start rounded-full px-4 py-1.5 text-[11px]" onClick={() => setJobId(null)}>
              ลองใหม่
            </button>
          )}
          {job.isError && <InsetPanel role="alert" className="text-down">อ่านสถานะ backtest ไม่ได้</InsetPanel>}
        </Card>
      )}

      <div className="flex justify-between">
        <button className="bg-surface shadow-raised-sm rounded-control px-5 py-3 disabled:opacity-50" disabled={step === 0} onClick={() => setStep(step - 1)}>
          Back
        </button>
        {step < 3 ? (
          <PrimaryButton disabled={step === 0 && !step1Ok} onClick={() => setStep(step + 1)}>
            Next
          </PrimaryButton>
        ) : (
          <PrimaryButton disabled={!canCreate || create.isPending} onClick={() => create.mutate()}>
            สร้างบอทและเริ่ม Paper
          </PrimaryButton>
        )}
      </div>
    </div>
  )
}
