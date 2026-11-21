import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TotpHost } from '../lib/totp'
import BotDetail from './bots/BotDetail'
import Bots from './bots/Bots'
import Wizard from './bots/Wizard'
import RiskSettings from './risk/RiskSettings'
import Trade from './trade/Trade'

vi.mock('../ui/PriceChart', async (orig) => ({
  ...(await orig<typeof import('../ui/PriceChart')>()),
  LineChart: () => <div data-testid="line-chart" />,
  PriceChart: () => <div data-testid="price-chart" />,
}))

type Handler = (init?: RequestInit, url?: string) => unknown | { __status: number; body: unknown }
const calls: { path: string; init?: RequestInit }[] = []

function mockApi(routes: Record<string, Handler>) {
  calls.length = 0
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = url.replace('/api/v1', '').split('?')[0]
      calls.push({ path, init })
      const h = routes[`${init?.method ?? 'GET'} ${path}`]
      if (!h) return new Response('{"detail":"not found"}', { status: 404 })
      const r = h(init, url) as { __status?: number; body?: unknown }
      return r && r.__status ? new Response(JSON.stringify(r.body), { status: r.__status }) : new Response(JSON.stringify(r), { status: 200 })
    }),
  )
}

function renderAt(path: string, ui: React.ReactNode = null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/bots" element={<Bots />} />
          <Route path="/bots/new" element={<Wizard />} />
          <Route path="/bots/:id" element={<BotDetail />} />
          <Route path="/settings" element={<RiskSettings />} />
          <Route path="/trade" element={<Trade />} />
        </Routes>
        <TotpHost />
        {ui}
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

const profile = { risk_per_trade: '0.005', max_positions: 4, max_symbol_exposure: '0.25', max_total_exposure: '0.8', max_open_risk: '0.02', max_bucket_risk: '0.0125', min_cash_reserve: '0.2', daily_loss: '0.02', weekly_loss: '0.05', max_drawdown: '0.12' }
const bot = { id: 'b1', name: 'alpha', account_id: 'a1', market: 'SPOT', symbols: ['BTCUSDT'], status: 'PAPER', mode: 'paper', config: { strategy: 's1', params: {}, version: 1 }, created_at: '2026-11-20T00:00:00Z' }
const emptyPerf = { n_trades: 0, win_rate: 0, profit_factor: null, expectancy_r: 0, net_pnl: '0', max_drawdown: 0, sharpe: 0, equity: [], drawdown: [] }

describe('Bots list', () => {
  it('shows the empty state with a way to create the first bot', async () => {
    mockApi({ 'GET /bots': () => [] })
    renderAt('/bots')
    expect(await screen.findByText('ยังไม่มีบอท — สร้างบอทแรกในโหมด Paper')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /New bot/ })).toBeInTheDocument()
  })
  it('lists bots with their status', async () => {
    mockApi({ 'GET /bots': () => [bot], 'GET /bots/b1/performance': () => emptyPerf })
    renderAt('/bots')
    expect(await screen.findByRole('link', { name: 'Open alpha' })).toHaveTextContent('PAPER')
  })
})

describe('Bot detail', () => {
  const base = {
    'GET /bots/b1': () => bot,
    'GET /bots/b1/performance': () => emptyPerf,
    'GET /signals': () => [],
    'GET /trades': () => [],
  }
  it('keeps Go live disabled and lists every failing gate', async () => {
    mockApi({
      ...base,
      'GET /bots/b1/gates': () => ({ allowed: false, checks: [{ name: 'gate1_backtest', ok: false, detail: 'no walk-forward backtest' }, { name: 'gate_b_live_enabled', ok: false, detail: 'live trading is disabled' }] }),
    })
    renderAt('/bots/b1')
    expect(await screen.findByText('no walk-forward backtest')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Go live' })).toBeDisabled()
    expect(screen.getAllByLabelText('not passed')).toHaveLength(2)
  })
  it('shows empty states for signals, trades and the equity curve', async () => {
    mockApi({ ...base, 'GET /bots/b1/gates': () => ({ allowed: false, checks: [] }) })
    renderAt('/bots/b1')
    expect(await screen.findByText('ยังไม่มีสัญญาณ')).toBeInTheDocument()
    expect(screen.getByText('ยังไม่มีเทรด — บอทยังไม่ได้เปิดสถานะ')).toBeInTheDocument()
  })
})

describe('Wizard', () => {
  it('cannot leave step 1 until name, account and symbols are chosen', async () => {
    mockApi({ 'GET /accounts': () => [{ id: 'a1', label: 'demo', exchange: 'binance', key_type: 'HMAC', is_testnet: true, api_key_last4: '1234', permissions_checked_at: '2026-11-20T00:00:00Z' }] })
    renderAt('/bots/new')
    const next = screen.getByRole('button', { name: 'Next' })
    expect(next).toBeDisabled()
    await userEvent.type(screen.getByLabelText('ชื่อบอท'), 'alpha')
    await userEvent.selectOptions(await screen.findByLabelText('บัญชี'), 'a1')
    expect(next).toBeEnabled()
  })
})

describe('Risk & Settings', () => {
  const base = {
    'GET /risk/profile': () => profile,
    'GET /risk/status': () => ({ kill_switch: false, entries_blocked: false, breakers: [], open_risk_cap_pct: '2.00' }),
    'GET /risk/events': () => [],
    'GET /accounts': () => [],
    'GET /settings/notifications': () => ({ telegram_configured: false, live_trading_enabled: false, trading_env: 'demo' }),
  }
  it('saving the risk profile asks for a TOTP code and sends it as X-TOTP', async () => {
    mockApi({ ...base, 'PUT /risk/profile': () => profile })
    renderAt('/settings')
    const slider = await screen.findByRole('slider', { name: /Risk per trade/ })
    const save = screen.getByRole('button', { name: 'Save' })
    expect(save).toBeDisabled()
    fireEvent.change(slider, { target: { value: '0.55' } }) // jsdom does not move range inputs with the keyboard
    await waitFor(() => expect(save).toBeEnabled())
    await userEvent.click(save)
    const dlg = await screen.findByRole('dialog')
    await userEvent.type(within(dlg).getByLabelText(/TOTP/), '123456')
    await userEvent.click(within(dlg).getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(calls.some((c) => c.init?.method === 'PUT')).toBe(true))
    const put = calls.find((c) => c.init?.method === 'PUT')!
    expect(new Headers(put.init?.headers).get('X-TOTP')).toBe('123456')
    expect(JSON.parse(String(put.init?.body)).risk_per_trade).toBe('0.0055')
  })
  it('cancelling the TOTP dialog sends nothing', async () => {
    mockApi({ ...base, 'PUT /risk/profile': () => profile })
    renderAt('/settings')
    const slider = await screen.findByRole('slider', { name: /Max positions/ })
    fireEvent.change(slider, { target: { value: '5' } })
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel' }))
    expect(calls.some((c) => c.init?.method === 'PUT')).toBe(false)
  })
  it('shows kill switch state and requires 2FA to reset it', async () => {
    mockApi({ ...base, 'GET /risk/status': () => ({ kill_switch: true, entries_blocked: true, breakers: [{ kind: 'KILL_SWITCH', detail: 'manual' }], open_risk_cap_pct: '2.00' }) })
    renderAt('/settings')
    expect(await screen.findByText(/KILL SWITCH ทำงานอยู่/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Reset \(2FA\)/ })).toBeInTheDocument()
  })
  it('shows API key problems returned by the server when a key is rejected', async () => {
    mockApi({ ...base, 'POST /accounts': () => ({ __status: 422, body: { detail: 'API key rejected' } }) })
    renderAt('/settings')
    await userEvent.click(await screen.findByRole('button', { name: 'Add key' }))
    await userEvent.type(screen.getByLabelText('Label'), 'demo')
    await userEvent.type(screen.getByLabelText('API key'), 'KEY-abcdef1234')
    await userEvent.type(screen.getByLabelText('API secret'), 'SECRET-xyz98765')
    await userEvent.click(screen.getByRole('button', { name: 'Verify & save' }))
    const dlg = await screen.findByRole('dialog')
    await userEvent.type(within(dlg).getByLabelText(/TOTP/), '123456')
    await userEvent.click(within(dlg).getByRole('button', { name: 'Confirm' }))
    expect(await screen.findByText('API key rejected', { selector: 'p' })).toBeInTheDocument()
  })
})


describe('Trade', () => {
  const approved = { approved: true, qty: '10', notional: '1000', risk_amount: '49.5', risk_pct_of_equity: '0.5000', entry: '100', stop: '95', tp1: '115', reasons: [], checks: [], adjustments: [] }
  const base = {
    'GET /markets/BTCUSDT/candles': () => [{ time: 1, open: 1, high: 2, low: 0.5, close: 1.5, volume: 3 }],
    'GET /markets/BTCUSDT/stats': () => ({ symbol: 'BTCUSDT', last: '100.5', change24h_pct: '1', high: '110', low: '90', volume: '5', funding_rate: null }),
    'GET /markets/BTCUSDT/depth': () => ({ symbol: 'BTCUSDT', bids: [{ price: '100', qty: '1' }], asks: [{ price: '101', qty: '1' }] }),
    'GET /orders': () => [],
  }
  const fill = async () => {
    await userEvent.type(await screen.findByLabelText(/Entry price/), '100')
    await userEvent.type(screen.getByLabelText(/Stop-loss/), '95')
    await userEvent.type(screen.getByLabelText(/Take profit/), '115')
  }
  it('shows the risk of the order as % of equity and only then enables Buy', async () => {
    mockApi({ ...base, 'POST /orders/preview': () => approved, 'POST /orders': () => ({ status: 'PROTECTED', detail: 'stop in place', client_order_id: 'x', preview: approved }) })
    renderAt('/trade')
    const buy = await screen.findByRole('button', { name: 'Buy BTC' })
    expect(buy).toBeDisabled() // nothing typed yet
    await fill()
    expect(await screen.findByText('0.50%', {}, { timeout: 3000 })).toBeInTheDocument()
    await waitFor(() => expect(buy).toBeEnabled())
    await userEvent.click(buy)
    await waitFor(() => expect(calls.some((c) => c.path === '/orders' && c.init?.method === 'POST')).toBe(true))
    const sent = JSON.parse(String(calls.find((c) => c.path === '/orders' && c.init?.method === 'POST')!.init?.body))
    expect(sent).toMatchObject({ symbol: 'BTCUSDT', order_type: 'LIMIT', entry: '100', stop: '95', tp1: '115' })
    expect(sent.qty).toBeUndefined() // the user never sets the size
  })
  it('shows every order the system placed in Order history, with its source', async () => {
    const row = { id: 'st1-e', symbol: 'BTCUSDT', side: 'BUY', type: 'MARKET', status: 'FILLED', price: '100.5', qty: '10', executed_qty: '10', ts: '2026-11-21T01:00:00Z', source: 'manual' }
    const stop = { ...row, id: 'st1-r0', side: 'SELL', type: 'STOP_LOSS_LIMIT', status: 'NEW', executed_qty: '0', source: 'bot:Alpha' }
    mockApi({ ...base, 'GET /orders': (_i, url) => (url?.includes('status=history') ? [row, stop] : []) })
    renderAt('/trade')
    expect(await screen.findByText('bot:Alpha')).toBeInTheDocument()
    expect(screen.getByText('manual')).toBeInTheDocument()
    expect(screen.getByText('stop loss limit')).toBeInTheDocument()
    expect(screen.getByText('10 / 10')).toBeInTheDocument()
  })
  it('lists the failed checks and keeps Buy disabled when the Risk Engine rejects', async () => {
    const rejected = { ...approved, approved: false, qty: '0', reasons: ['RR_TOO_LOW'], checks: [{ name: 'risk_reward', passed: false, detail: 'R:R 0.6 < 1.5' }] }
    mockApi({ ...base, 'POST /orders/preview': () => rejected })
    renderAt('/trade')
    await fill()
    expect(await screen.findByText(/risk_reward: R:R 0.6 < 1.5/, {}, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Buy BTC' })).toBeDisabled()
  })
})
