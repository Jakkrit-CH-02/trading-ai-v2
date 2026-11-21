import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../../lib/api'
import { askTotp } from '../../lib/totp'
import { Card, CardState, InsetPanel, useToasts } from '../../ui'
import { useMlModels, type MlModel } from './queries'

const STATUS: Record<string, string> = { active: 'ใช้งานอยู่', candidate: 'ยังไม่ผ่านเกณฑ์', retired: 'ปลดแล้ว', suspended: 'ถูกปิดอัตโนมัติ' }
const fmt = (n: number | null | undefined) => (n == null ? '—' : n.toFixed(3))
type Bt = { baseline?: { expectancy_r?: number; trades?: number }; with_ml?: { expectancy_r?: number; trades?: number }; improves?: boolean } | null

function Row({ m }: { m: MlModel }) {
  const bt = m.backtest as Bt
  return (
    <InsetPanel className="flex flex-col gap-1 text-[13px]">
      <div className="flex items-baseline justify-between gap-3">
        <strong>
          {m.strategy} v{m.version} · {STATUS[m.status] ?? m.status}
        </strong>
        <span className="text-secondary text-[11px]">
          {m.n_samples} สัญญาณ · {m.trained_from.slice(0, 10)} → {m.trained_to.slice(0, 10)}
        </span>
      </div>
      <div className="text-secondary text-[12px]">
        AUC cross-validation {fmt(m.cv_auc)} · AUC holdout {fmt(m.holdout_auc)} (0.5 = เดาสุ่ม)
        {bt?.baseline && bt.with_ml ? ` · backtest นอกตัวอย่าง: ${fmt(bt.baseline.expectancy_r)}R → ${fmt(bt.with_ml.expectancy_r)}R ต่อเทรด (${bt.baseline.trades} → ${bt.with_ml.trades} เทรด)` : ''}
      </div>
      {m.reason && <div className="text-secondary text-[12px]">{m.reason}</div>}
      {m.note && <div className="text-down text-[12px]">{m.note}</div>}
    </InsetPanel>
  )
}

export default function MlCard() {
  const q = useMlModels()
  const qc = useQueryClient()
  const toast = useToasts((s) => s.push)
  const active = q.data?.filter((m) => m.status === 'active') ?? []
  const rollback = useMutation({
    mutationFn: async (strategy: string) => {
      const totp = await askTotp('Rollback ML model', `ย้อน ${strategy} กลับไปใช้โมเดลเวอร์ชันก่อนหน้า`)
      return totp ? api(`/ml/${strategy}/rollback`, { method: 'POST', totp }) : null
    },
    onSuccess: (r) => {
      if (r) {
        toast('info', 'ย้อนโมเดลแล้ว')
        void qc.invalidateQueries({ queryKey: ['ml-models'] })
      }
    },
    onError: (e) => toast('error', e instanceof ApiError ? e.message : 'ย้อนโมเดลไม่สำเร็จ'),
  })
  return (
    <Card title="ML signal model" subtitle="LightGBM ให้คะแนน S_ml ต่อสัญญาณ · ใช้จริงก็ต่อเมื่อชนะบน backtest นอกตัวอย่าง · ถ้าไม่มีโมเดลที่ใช้งาน S_ml = 50 (เป็นกลาง)">
      <CardState status={q.isPending ? 'loading' : q.isError ? 'error' : q.data?.length ? 'ready' : 'empty'} empty="ยังไม่เคยเทรนโมเดล — รัน softtrade ml-train --strategy s1" onRetry={() => q.refetch()}>
        <div className="flex flex-col gap-3">
          {active.length === 0 && <InsetPanel className="text-secondary text-[13px]">ตอนนี้ไม่มีโมเดลที่ใช้งาน — ทุกสัญญาณได้ S_ml = 50 เหมือนเดิม</InsetPanel>}
          {q.data?.map((m) => <Row key={`${m.strategy}-${m.version}`} m={m} />)}
          {active.map((m) => (
            <button key={m.strategy} className="text-secondary self-start underline" onClick={() => rollback.mutate(m.strategy)}>
              Rollback {m.strategy} ไปเวอร์ชันก่อนหน้า
            </button>
          ))}
        </div>
      </CardState>
    </Card>
  )
}
