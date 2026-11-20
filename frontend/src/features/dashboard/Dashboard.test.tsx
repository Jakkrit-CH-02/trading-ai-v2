import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Dashboard from './Dashboard'

vi.mock('../../ui/PriceChart', () => ({ PriceChart: () => <div data-testid="price-chart" /> }))

class FakeWs {
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  send() {}
  close() {}
}

type Routes = Record<string, () => { status?: number; body: unknown }>

const ok = {
  summary: { connected: true, mode: 'paper', equity: '128460.72', pnl_today: '3214.08', pnl_today_pct: '2.56', available: '20553.10', in_orders: '4180.00', allocation: [{ label: 'BTC', pct: 46 }, { label: 'Cash', pct: 54 }] },
  stats: { symbol: 'BTCUSDT', last: '97412.50', change24h_pct: '2.84', high: '98120', low: '94305.4', volume: '32800', funding_rate: null },
  candles: [{ time: 1, open: 1, high: 2, low: 0.5, close: 1.5, volume: 3 }],
  watch: [{ symbol: 'BTCUSDT', name: 'Bitcoin', last: '97412.50', change24h_pct: '2.84', spark: [1, 2, 3] }],
  sentiment: { value: 68, label: 'Greed' },
  bots: { bots: [], running: 0, open_risk_pct: '0', open_risk_cap_pct: '2.00' },
  orders: [{ id: 'a1', symbol: 'BTCUSDT', side: 'BUY', type: 'LIMIT', status: 'NEW', price: '96850', qty: '0.042', executed_qty: '0', ts: '2026-11-20T03:42:00Z', source: null }],
}

function mockApi(overrides: Routes = {}) {
  const routes: Routes = {
    '/dashboard/summary': () => ({ body: ok.summary }),
    '/markets/BTCUSDT/stats': () => ({ body: ok.stats }),
    '/markets/BTCUSDT/candles': () => ({ body: ok.candles }),
    '/watchlist': () => ({ body: ok.watch }),
    '/sentiment': () => ({ body: ok.sentiment }),
    '/bots/summary': () => ({ body: ok.bots }),
    '/orders': () => ({ body: ok.orders }),
    ...overrides,
  }
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = url.replace('/api/v1', '').split('?')[0]
    const h = routes[path]
    if (!h) return new Response('not found', { status: 404 })
    const { status = 200, body } = h()
    return new Response(JSON.stringify(body), { status })
  }))
}

function renderDash() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.stubGlobal('WebSocket', FakeWs)
})
afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Dashboard', () => {
  it('shows skeletons first, then every card with real values', async () => {
    mockApi()
    renderDash()
    expect(screen.getAllByRole('status').length).toBeGreaterThan(0)
    expect(await screen.findByText('$128,460')).toBeInTheDocument()
    expect(screen.getByText('.72')).toBeInTheDocument()
    expect(screen.getByText('+3,214.08')).toBeInTheDocument()
    expect(screen.getByText('$20,553.10')).toBeInTheDocument()
    expect(await screen.findByText('Greed')).toBeInTheDocument()
    expect(await screen.findByRole('img', { name: 'BTC 46%' })).toBeInTheDocument()
    const orders = await screen.findByRole('table')
    expect(within(orders).getByText('96,850.00')).toBeInTheDocument()
    expect(within(orders).getByText('Open')).toBeInTheDocument()
    expect(screen.getByText('0 bots running')).toBeInTheDocument()
  })

  it('shows the not-connected empty state when no trading account is configured', async () => {
    mockApi({ '/dashboard/summary': () => ({ body: { connected: false, mode: 'paper', equity: '0', available: '0', in_orders: '0', allocation: [] } }) })
    renderDash()
    expect(await screen.findByText(/ยังไม่ได้เชื่อมบัญชี Demo/)).toBeInTheDocument()
    expect(await screen.findByText('ยังไม่มีสินทรัพย์ในพอร์ต')).toBeInTheDocument()
  })

  it('shows a per-card error with retry instead of breaking the page', async () => {
    mockApi({ '/sentiment': () => ({ status: 502, body: {} }), '/orders': () => ({ body: [] }) })
    renderDash()
    expect(await screen.findByRole('alert')).toHaveTextContent('โหลดข้อมูลไม่สำเร็จ')
    expect(screen.getByRole('button', { name: 'ลองใหม่' })).toBeInTheDocument()
    expect(await screen.findByText('ยังไม่มีออเดอร์')).toBeInTheDocument() // other cards still render
    expect(await screen.findByText('$128,460')).toBeInTheDocument()
  })
})
