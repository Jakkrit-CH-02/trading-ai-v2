import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, ApiError, num, type Schemas } from '../../lib/api'
import { askTotp } from '../../lib/totp'
import { Card, CardState, ConfirmDialog, DataTable, InsetPanel, PrimaryButton, Skeleton, Slider, TextInput, useToasts } from '../../ui'

type Profile = Schemas['RiskProfileOut-Output']
const fail = (e: unknown) => useToasts.getState().push('error', e instanceof ApiError ? e.message : 'เกิดข้อผิดพลาด')
const FIELDS: { key: keyof Profile; label: string; min: number; max: number; step: number; unit?: string; pct?: boolean; hint: string }[] = [
  { key: 'risk_per_trade', label: 'Risk per trade', min: 0.1, max: 1, step: 0.05, pct: true, hint: 'เพดานตาม SPEC คือ 1%' },
  { key: 'max_positions', label: 'Max positions', min: 1, max: 10, step: 1, unit: '', hint: 'จำนวนสถานะเปิดพร้อมกัน' },
  { key: 'max_symbol_exposure', label: 'Max per symbol', min: 5, max: 50, step: 1, pct: true, hint: 'สัดส่วนพอร์ตต่อเหรียญ' },
  { key: 'max_total_exposure', label: 'Max total exposure', min: 10, max: 95, step: 1, pct: true, hint: 'รวมทุกเหรียญ (Spot)' },
  { key: 'max_open_risk', label: 'Max open risk', min: 0.5, max: 5, step: 0.25, pct: true, hint: 'ผลรวมความเสี่ยงของทุกสถานะ' },
  { key: 'max_bucket_risk', label: 'Max bucket risk', min: 0.25, max: 3, step: 0.25, pct: true, hint: 'กลุ่มเหรียญที่เคลื่อนไหวคล้ายกัน' },
  { key: 'min_cash_reserve', label: 'Min cash reserve', min: 5, max: 50, step: 1, pct: true, hint: 'เงินสดขั้นต่ำที่ต้องเหลือ' },
  { key: 'daily_loss', label: 'Daily loss limit', min: 0.5, max: 5, step: 0.25, pct: true, hint: 'ถึงแล้วหยุดเปิดออเดอร์ถึงเที่ยงคืน UTC' },
  { key: 'weekly_loss', label: 'Weekly loss limit', min: 1, max: 10, step: 0.5, pct: true, hint: 'ถึงแล้วหยุด 7 วัน' },
  { key: 'max_drawdown', label: 'Max drawdown (kill)', min: 5, max: 30, step: 1, pct: true, hint: 'ถึงแล้ว Kill switch ทำงาน' },
]

const toForm = (p: Profile) => Object.fromEntries(FIELDS.map((f) => [f.key, f.pct ? +(num(p[f.key]) * 100).toFixed(2) : num(p[f.key])]))

function RiskProfileCard() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['risk-profile'], queryFn: () => api<Profile>('/risk/profile') })
  // only the user's edits are state; the form is derived from the server value plus those edits
  const [edits, setEdits] = useState<Record<string, number>>({})
  const form = q.data ? { ...toForm(q.data), ...edits } : null
  const dirty = !!q.data && Object.entries(edits).some(([k, v]) => v !== toForm(q.data)[k])
  const save = useMutation({
    mutationFn: async () => {
      const totp = await askTotp('ยืนยันการแก้ Risk profile', 'การเปลี่ยนค่าความเสี่ยงต้องใช้รหัส 2FA')
      if (!totp || !form) return null
      const body = Object.fromEntries(FIELDS.map((f) => [f.key, f.pct ? String(+(form[f.key] / 100).toFixed(6)) : form[f.key]]))
      return api<Profile>('/risk/profile', { method: 'PUT', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' }, totp })
    },
    onSuccess: (r) => {
      if (r) {
        useToasts.getState().push('info', 'บันทึก Risk profile แล้ว')
        setEdits({})
        void qc.invalidateQueries({ queryKey: ['risk-profile'] })
      }
    },
    onError: fail,
  })
  return (
    <Card title="Risk profile" subtitle="ค่าเริ่มต้นตาม SPEC 3 · ต้องใช้ 2FA ทุกครั้งที่บันทึก" className="xl:col-span-2">
      <CardState status={q.isPending ? 'loading' : q.isError ? 'error' : 'ready'} onRetry={() => q.refetch()} skeleton={<Skeleton className="h-64" />}>
        {form && (
          <>
            <div className="grid gap-x-8 gap-y-5 md:grid-cols-2">
              {FIELDS.map((f) => (
                <Slider key={f.key} label={f.label} value={form[f.key]} min={f.min} max={f.max} step={f.step} unit={f.unit ?? '%'} hint={f.hint} onChange={(v) => setEdits({ ...edits, [f.key]: v })} />
              ))}
            </div>
            <div className="flex justify-end gap-3">
              <button className="bg-surface shadow-raised-sm rounded-control px-4 py-2 disabled:opacity-50" disabled={!dirty} onClick={() => setEdits({})}>
                Reset
              </button>
              <PrimaryButton disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
                Save
              </PrimaryButton>
            </div>
          </>
        )}
      </CardState>
    </Card>
  )
}

function BreakersCard() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['risk-status'], queryFn: () => api<Schemas['RiskStatus']>('/risk/status'), refetchInterval: 5000 })
  const [confirm, setConfirm] = useState(false)
  const refresh = () => qc.invalidateQueries({ queryKey: ['risk-status'] }).then(() => qc.invalidateQueries({ queryKey: ['risk-events'] }))
  const kill = useMutation({
    mutationFn: () => api('/risk/kill', { method: 'POST', body: JSON.stringify({ reason: 'manual (UI)' }), headers: { 'Content-Type': 'application/json' } }),
    onSuccess: refresh,
    onError: fail,
  })
  const reset = useMutation({
    mutationFn: async () => {
      const totp = await askTotp('Reset kill switch', 'บอทที่ถูก KILLED จะกลับเป็น PAUSED ไม่เริ่มเองอัตโนมัติ')
      return totp ? api('/risk/kill/reset', { method: 'POST', totp }) : null
    },
    onSuccess: refresh,
    onError: fail,
  })
  const d = q.data
  return (
    <Card title="Circuit breakers" subtitle="สถานะ Kill switch และตัวตัดการเทรด">
      <CardState status={cardState(q)} onRetry={() => q.refetch()} skeleton={<Skeleton className="h-32" />}>
        {d && (
          <>
            <InsetPanel className={d.kill_switch ? 'text-down font-semibold' : ''}>
              {d.kill_switch ? 'KILL SWITCH ทำงานอยู่ — ไม่มีการเปิดออเดอร์ใหม่' : d.entries_blocked ? 'หยุดเปิดออเดอร์ใหม่ชั่วคราว' : 'ปกติ — ไม่มีตัวตัดการเทรดทำงาน'}
            </InsetPanel>
            {d.breakers.map((b) => (
              <div key={b.kind} className="text-[13px]">
                <strong>{b.kind}</strong> <span className="text-secondary">{b.detail}</span>
              </div>
            ))}
            <div className="flex gap-3">
              {d.kill_switch ? (
                <PrimaryButton onClick={() => reset.mutate()}>Reset (2FA)</PrimaryButton>
              ) : (
                <button className="bg-surface shadow-raised-sm text-down rounded-control px-5 py-3 font-semibold" onClick={() => setConfirm(true)}>
                  Kill switch
                </button>
              )}
            </div>
          </>
        )}
      </CardState>
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="หยุดทุกบอททันที?" description="บอททั้งหมดจะเป็น KILLED และไม่เปิดออเดอร์ใหม่จนกว่าจะ Reset ด้วย 2FA" confirmLabel="Kill" onConfirm={() => kill.mutate()} />
    </Card>
  )
}

function cardState(q: { isPending: boolean; isError: boolean }) {
  return q.isPending ? 'loading' : q.isError ? 'error' : 'ready'
}

function EventsCard() {
  const q = useQuery({ queryKey: ['risk-events'], queryFn: () => api<Schemas['RiskEventOut'][]>('/risk/events'), refetchInterval: 15_000 })
  return (
    <Card title="Risk events" subtitle="เหตุการณ์ความเสี่ยงล่าสุด" className="xl:col-span-2">
      <CardState status={q.isPending ? 'loading' : q.isError ? 'error' : q.data?.length ? 'ready' : 'empty'} empty="ยังไม่มีเหตุการณ์" onRetry={() => q.refetch()}>
        <DataTable
          rowKey={(e) => e.id}
          rows={q.data ?? []}
          columns={[
            { key: 'time', header: 'Time', render: (e) => new Date(e.ts).toLocaleString('en-GB') },
            { key: 'type', header: 'Type', render: (e) => <strong>{e.type}</strong> },
            { key: 'sev', header: 'Severity', render: (e) => (e.severity === 'critical' ? <span className="text-down font-semibold">{e.severity}</span> : e.severity) },
            { key: 'detail', header: 'Detail', render: (e) => String((e.payload as { reason?: string }).reason ?? '—') },
            { key: 'res', header: 'Resolved', render: (e) => (e.resolved_at ? 'Yes' : '—') },
          ]}
        />
      </CardState>
    </Card>
  )
}

function AccountsCard() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['accounts'], queryFn: () => api<Schemas['AccountOut'][]>('/accounts') })
  const [open, setOpen] = useState(false)
  const [f, setF] = useState({ label: '', api_key: '', api_secret: '' })
  const [problems, setProblems] = useState<string[]>([])
  const add = useMutation({
    mutationFn: async () => {
      const totp = await askTotp('เพิ่ม API key', 'ระบบจะตรวจสิทธิ์ key ก่อนบันทึก และปฏิเสธ key ที่ถอนเงินได้')
      if (!totp) return null
      setProblems([])
      return api('/accounts', { method: 'POST', body: JSON.stringify({ ...f, is_testnet: true }), headers: { 'Content-Type': 'application/json' }, totp })
    },
    onSuccess: (r) => {
      if (r) {
        setF({ label: '', api_key: '', api_secret: '' })
        setOpen(false)
        void qc.invalidateQueries({ queryKey: ['accounts'] })
      }
    },
    onError: (e) => {
      const msg = e instanceof ApiError ? e.message : ''
      setProblems(msg ? [msg] : [])
      fail(e)
    },
  })
  const verify = useMutation({
    mutationFn: (id: string) => api(`/accounts/${id}/verify`, { method: 'POST' }),
    onSuccess: () => {
      useToasts.getState().push('info', 'key ผ่านการตรวจสิทธิ์')
      void qc.invalidateQueries({ queryKey: ['accounts'] })
    },
    onError: (e) => {
      fail(e)
      void qc.invalidateQueries({ queryKey: ['accounts'] })
    },
  })
  return (
    <Card title="API keys" subtitle="Demo / Testnet เท่านั้น · key ต้องถอนเงินไม่ได้" action={<button className="bg-surface shadow-raised-sm rounded-full px-4 py-1.5 text-[11px]" onClick={() => setOpen(!open)}>{open ? 'Cancel' : 'Add key'}</button>}>
      <CardState status={q.isPending ? 'loading' : q.isError ? 'error' : q.data?.length || open ? 'ready' : 'empty'} empty="ยังไม่มีบัญชี — เพิ่ม API key ของ Binance Demo" onRetry={() => q.refetch()}>
        {q.data?.map((a) => (
          <InsetPanel key={a.id} className="flex items-center justify-between gap-3">
            <span>
              <strong>{a.label}</strong>
              <span className="text-secondary block text-[11px]">
                {a.key_type} · …{a.api_key_last4} · {a.is_testnet ? 'Demo/Testnet' : 'Live'} · {a.permissions_checked_at ? `ตรวจแล้ว ${new Date(a.permissions_checked_at).toLocaleDateString('en-GB')}` : 'ยังไม่ผ่านการตรวจ'}
              </span>
            </span>
            <button className="bg-surface shadow-raised-sm rounded-full px-4 py-1.5 text-[11px]" onClick={() => verify.mutate(a.id)}>
              Verify
            </button>
          </InsetPanel>
        ))}
        {open && (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault()
              add.mutate()
            }}
          >
            <TextInput label="Label" value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} required />
            <TextInput label="API key" value={f.api_key} onChange={(e) => setF({ ...f, api_key: e.target.value })} autoComplete="off" required />
            <TextInput label="API secret" type="password" value={f.api_secret} onChange={(e) => setF({ ...f, api_secret: e.target.value })} autoComplete="off" required />
            {problems.map((p) => (
              <p key={p} role="alert" className="text-down text-[13px]">{p}</p>
            ))}
            <PrimaryButton type="submit" disabled={add.isPending}>Verify & save</PrimaryButton>
          </form>
        )}
      </CardState>
    </Card>
  )
}

function NotificationsCard() {
  const q = useQuery({ queryKey: ['notif'], queryFn: () => api<{ telegram_configured: boolean; live_trading_enabled: boolean; trading_env: string }>('/settings/notifications') })
  const test = useMutation({ mutationFn: () => api('/settings/notifications/test', { method: 'POST' }), onSuccess: () => useToasts.getState().push('info', 'ส่งข้อความทดสอบแล้ว'), onError: fail })
  return (
    <Card title="Notifications" subtitle="Telegram (ตั้งค่า TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID ใน .env)">
      <CardState status={cardState(q)} onRetry={() => q.refetch()} skeleton={<Skeleton className="h-20" />}>
        {q.data && (
          <>
            <InsetPanel>{q.data.telegram_configured ? 'Telegram เชื่อมแล้ว' : 'ยังไม่ได้ตั้งค่า Telegram — ไม่มีการแจ้งเตือน'}</InsetPanel>
            <div className="text-secondary text-[11px]">ระบบเทรด: {q.data.trading_env} · Live {q.data.live_trading_enabled ? 'เปิด' : 'ปิด (ก่อน Gate B)'}</div>
            <button className="bg-surface shadow-raised-sm self-start rounded-full px-4 py-1.5 text-[11px] disabled:opacity-50" disabled={!q.data.telegram_configured} onClick={() => test.mutate()}>
              Send test
            </button>
          </>
        )}
      </CardState>
    </Card>
  )
}

function SecurityCard() {
  const [secret, setSecret] = useState<Schemas['TotpSetupOut'] | null>(null)
  const rotate = useMutation({
    mutationFn: async () => {
      const totp = await askTotp('เปลี่ยน 2FA secret', 'ใส่รหัสปัจจุบัน secret เดิมจะใช้ไม่ได้ทันที')
      return totp ? api<Schemas['TotpSetupOut']>('/auth/totp/setup', { method: 'POST', totp }) : null
    },
    onSuccess: (r) => r && setSecret(r),
    onError: fail,
  })
  return (
    <Card title="Two-factor (TOTP)" subtitle="เปลี่ยน secret เมื่อเปลี่ยนเครื่องหรือสงสัยว่ารั่ว">
      <button className="bg-surface shadow-raised-sm self-start rounded-full px-4 py-1.5 text-[11px]" onClick={() => rotate.mutate()}>
        Rotate secret
      </button>
      {secret && (
        <InsetPanel className="flex flex-col gap-2 break-all">
          <span className="text-secondary text-[11px]">แสดงครั้งเดียว — เพิ่มลง authenticator ทันที</span>
          <code className="text-[13px] font-semibold">{secret.secret}</code>
          <code className="text-secondary text-[11px]">{secret.uri}</code>
          <button className="bg-surface shadow-raised-sm self-start rounded-full px-4 py-1.5 text-[11px]" onClick={() => setSecret(null)}>
            Done
          </button>
        </InsetPanel>
      )}
    </Card>
  )
}

export default function RiskSettings() {
  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
      <RiskProfileCard />
      <BreakersCard />
      <EventsCard />
      <AccountsCard />
      <NotificationsCard />
      <SecurityCard />
    </div>
  )
}
