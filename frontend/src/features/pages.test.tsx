import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TotpHost } from '../lib/totp'
import { Toaster } from '../ui'
import { parseSse } from './ai/chat'
import AiAnalyst from './ai/AiAnalyst'
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

type Handler = (init?: RequestInit, url?: string) => unknown | { __status: number; body: unknown } | { __sse: string }
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
      const r = h(init, url) as { __status?: number; body?: unknown; __sse?: string }
      if (r && r.__sse !== undefined) return new Response(r.__sse, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
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
          <Route path="/ai" element={<AiAnalyst />} />
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
    'GET /bots/b1/logs': () => [],
    'GET /runner/status': () => ({ alive: true, last_beat: '2026-11-21T00:00:00Z', age_s: 3 }),
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
  it('shows the activity log, filterable by kind', async () => {
    const logs = [
      { ts: '2026-11-21T02:00:00Z', kind: 'trade', level: 'warning', title: 'Closed BTCUSDT: stop', detail: '-5.00 USDT (-1.00R)' },
      { ts: '2026-11-21T01:00:00Z', kind: 'risk', level: 'critical', title: 'UNPROTECTED_POSITION', detail: 'symbol=BTCUSDT' },
      { ts: '2026-11-21T00:00:00Z', kind: 'audit', level: 'info', title: 'bot.start', detail: 'status=PAPER' },
    ]
    mockApi({ ...base, 'GET /bots/b1/logs': () => logs, 'GET /bots/b1/gates': () => ({ allowed: false, checks: [] }) })
    renderAt('/bots/b1')
    expect(await screen.findByText('Closed BTCUSDT: stop')).toBeInTheDocument()
    expect(screen.getByText('UNPROTECTED_POSITION')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('radio', { name: 'Risk' }))
    expect(screen.queryByText('Closed BTCUSDT: stop')).not.toBeInTheDocument()
    expect(screen.getByText('UNPROTECTED_POSITION')).toBeInTheDocument()
  })
  it('stays quiet about the runner while it is alive', async () => {
    mockApi({ ...base, 'GET /bots/b1/gates': () => ({ allowed: false, checks: [] }) })
    renderAt('/bots/b1')
    await screen.findByText('ยังไม่มีสัญญาณ')
    await waitFor(() => expect(calls.some((c) => c.path === '/runner/status')).toBe(true))
    expect(screen.queryByText(/ไม่ตอบสนอง/)).not.toBeInTheDocument()
  })
  it('shows proof of life: heartbeat, the last candle judged and the next one due', async () => {
    const at = new Date(Date.now() - 5 * 60_000).toISOString()
    mockApi({
      ...base,
      'GET /runner/status': () => ({ alive: true, last_beat: at, age_s: 4, evaluated: [{ symbol: 'BTCUSDT', interval: '1h', bar_time: at, processed_at: at }] }),
      'GET /bots/b1/gates': () => ({ allowed: false, checks: [] }),
    })
    renderAt('/bots/b1')
    expect(await screen.findByText(/Runner ทำงานอยู่/)).toBeInTheDocument()
    expect(screen.getByText(/ตรวจแท่ง 1h ของ BTCUSDT/)).toBeInTheDocument()
    expect(screen.getByText(/แท่งถัดไปปิด/)).toBeInTheDocument()
  })
  it('warns when an active bot has no live runner', async () => {
    mockApi({ ...base, 'GET /runner/status': () => ({ alive: false, last_beat: null, age_s: null }), 'GET /bots/b1/gates': () => ({ allowed: false, checks: [] }) })
    renderAt('/bots/b1')
    expect(await screen.findByText(/ไม่ตอบสนอง/)).toBeInTheDocument()
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

describe('AI Analyst', () => {
  const brief = { id: 'x1', symbol: 'BTCUSDT', created_at: '2026-11-21T06:00:00Z', model: 'claude-sonnet-5-5', bias: 'bull', s_ai: 72, support: [55000], resistance: [60000], risks: ['funding สูง'], summary_th: ['บรรทัดแรก', 'บรรทัดสอง', 'บรรทัดสาม'], cost_usd: '0.01' }
  const status = { worker_alive: true, key_configured: true, month_spend_usd: '1.50', budget_usd: 20, last_news_at: null }
  const news = [{ id: 'n1', source: 'CoinDesk', title: 'ETF approved', url: 'https://x.test/a', published_at: '2026-11-21T05:00:00Z', symbols: ['BTC'], sentiment: 0.6, severity: 0.4, category: 'regulation' }]

  it('shows the brief, the spend and the headlines', async () => {
    mockApi({ 'GET /ai/briefs': () => [brief], 'GET /ai/news': () => news, 'GET /ai/status': () => status, 'GET /ai/reviews': () => [], 'GET /ml/models': () => [] })
    renderAt('/ai')
    expect(await screen.findByText('บรรทัดแรก')).toBeInTheDocument()
    expect(screen.getByText(/Bullish · S_ai 72/)).toBeInTheDocument()
    expect(screen.getByText(/ค่าใช้จ่ายเดือนนี้ \$1.50 \/ \$20/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'ETF approved' })).toHaveAttribute('href', 'https://x.test/a')
    expect(screen.getByText(/ไม่มีสิทธิ์ส่งออเดอร์/)).toBeInTheDocument()
  })

  it('explains a missing key and an empty state instead of a blank page', async () => {
    mockApi({ 'GET /ai/briefs': () => [], 'GET /ai/news': () => [], 'GET /ai/status': () => ({ ...status, key_configured: false }) })
    renderAt('/ai')
    expect(await screen.findByText(/ยังไม่ได้ตั้ง ANTHROPIC_API_KEY/)).toBeInTheDocument()
    expect(screen.getByText('ยังไม่มี brief ของ BTC')).toBeInTheDocument()
  })

  it('warns when the worker is down and says the bots are unaffected', async () => {
    mockApi({ 'GET /ai/briefs': () => [], 'GET /ai/news': () => [], 'GET /ai/status': () => ({ ...status, worker_alive: false }) })
    renderAt('/ai')
    expect(await screen.findByText('AI worker ไม่ตอบสนอง')).toBeInTheDocument()
    expect(screen.getByText(/บอทเทรดไม่ได้รับผลกระทบ/)).toBeInTheDocument()
  })

  it('queues a refresh for the selected coin and reports a rate limit', async () => {
    let n = 0
    mockApi({
      'GET /ai/briefs': () => [brief],
      'GET /ai/news': () => news,
      'GET /ai/status': () => status,
      'POST /ai/briefs/refresh': () => (n++ === 0 ? { status: 'queued' } : { __status: 429, body: { detail: 'refreshed a moment ago' } }),
    })
    renderAt('/ai', <Toaster />)
    await screen.findByText('บรรทัดแรก')
    await userEvent.click(screen.getByRole('button', { name: 'Refresh brief' }))
    await waitFor(() => expect(calls.find((c) => c.path === '/ai/briefs/refresh')?.init?.body).toBe(JSON.stringify({ symbol: 'BTCUSDT' })))
    await userEvent.click(screen.getByRole('button', { name: 'Refresh brief' }))
    expect(await screen.findByText('refreshed a moment ago')).toBeInTheDocument()
  })

  const sse = (...evs: object[]) => ({ __sse: evs.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('') })
  const aiBase = { 'GET /ai/briefs': () => [brief], 'GET /ai/news': () => news, 'GET /ai/status': () => status, 'GET /ai/reviews': () => [], 'GET /ml/models': () => [] }

  it('parses SSE frames, keeps a partial frame for later and skips a broken one', () => {
    const a = parseSse('data: {"type":"delta","text":"a"}\n\ndata: {"type":"do')
    expect(a.events).toEqual([{ type: 'delta', text: 'a' }])
    expect(a.rest).toBe('data: {"type":"do')
    const b = parseSse(`${a.rest}ne"}\n\ndata: not json\n\n`)
    expect(b.events).toEqual([{ type: 'done' }])
  })

  it('streams an answer, shows the tool used, and a pause proposal needs a click', async () => {
    mockApi({
      ...aiBase,
      'POST /ai/chat': () => sse({ type: 'tool', name: 'get_bot_stats' }, { type: 'delta', text: 'บอท ' }, { type: 'delta', text: 'ปกติดี' }, { type: 'proposal', action: 'pause_bot', bot_id: 'b1', bot_name: 'alpha', reason: 'DD สูง' }, { type: 'done' }),
      'POST /bots/b1/pause': () => ({ ...bot, status: 'PAUSED' }),
    })
    renderAt('/ai', <Toaster />)
    await screen.findByText('บรรทัดแรก')
    await userEvent.type(screen.getByLabelText('Ask the AI'), 'บอทเป็นไง')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText(/บอท ปกติดี/)).toBeInTheDocument()
    expect(screen.getByText('ดูสถิติบอท')).toBeInTheDocument()
    expect(JSON.parse(String(calls.find((c) => c.path === '/ai/chat')?.init?.body))).toEqual({ messages: [{ role: 'user', content: 'บอทเป็นไง' }] })
    const box = await screen.findByRole('group', { name: 'AI proposal' })
    expect(within(box).getByText(/AI เสนอให้หยุดบอท alpha/)).toBeInTheDocument()
    expect(calls.some((c) => c.path === '/bots/b1/pause')).toBe(false) // nothing happens by itself
    await userEvent.click(within(box).getByRole('button', { name: 'ยืนยัน Pause' }))
    await waitFor(() => expect(calls.some((c) => c.path === '/bots/b1/pause' && c.init?.method === 'POST')).toBe(true))
    expect(await screen.findByText(/หยุดแล้ว/)).toBeInTheDocument()
  })

  it('dismissing a proposal changes nothing', async () => {
    mockApi({ ...aiBase, 'POST /ai/chat': () => sse({ type: 'proposal', action: 'pause_bot', bot_id: 'b1', bot_name: 'alpha', reason: 'x' }, { type: 'done' }) })
    renderAt('/ai')
    await screen.findByText('บรรทัดแรก')
    await userEvent.type(screen.getByLabelText('Ask the AI'), 'q')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    await userEvent.click(await screen.findByRole('button', { name: 'ไม่ต้อง' }))
    expect(screen.queryByRole('group', { name: 'AI proposal' })).not.toBeInTheDocument()
    expect(calls.some((c) => c.path === '/bots/b1/pause')).toBe(false)
  })

  it('explains an unavailable AI instead of failing silently', async () => {
    mockApi({ ...aiBase, 'POST /ai/chat': () => ({ __status: 503, body: { detail: 'worker down' } }) })
    renderAt('/ai')
    await screen.findByText('บรรทัดแรก')
    await userEvent.type(screen.getByLabelText('Ask the AI'), 'q')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText(/AI ยังไม่พร้อม/)).toBeInTheDocument()
  })

  it('lists the trade journal', async () => {
    const reviews = [
      { id: 'r1', kind: 'trade', created_at: '2026-11-21T06:00:00Z', symbol: 'BTCUSDT', verdict: 'win_clean', text: 'เข้าตามแผน', points: ['รอจังหวะ'], pnl_r: 1.5 },
      { id: 'r2', kind: 'week', created_at: '2026-11-17T00:00:00Z', symbol: null, verdict: null, text: 'สัปดาห์นี้เล็ก', points: ['ตัวอย่างน้อย'], pnl_r: -0.5 },
    ]
    mockApi({ ...aiBase, 'GET /ai/reviews': () => reviews })
    renderAt('/ai')
    expect(await screen.findByText(/BTCUSDT · ชนะอย่างมีเหตุผล/)).toBeInTheDocument()
    expect(screen.getByText('+1.50R', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('สรุปรายสัปดาห์')).toBeInTheDocument()
    expect(screen.getByText('ตัวอย่างน้อย')).toBeInTheDocument()
  })

  const mlModels = [
    { strategy: 'S1', version: 2, status: 'candidate', created_at: '2026-11-21T10:00:00Z', trained_from: '2023-12-27T00:00:00Z', trained_to: '2026-10-20T00:00:00Z', n_samples: 889, cv_auc: 0.58, holdout_auc: 0.616, backtest: { baseline: { expectancy_r: -0.087, trades: 132 }, with_ml: { expectancy_r: -0.058, trades: 125 }, improves: false }, reason: 'out-of-sample backtest does not improve', note: null },
    { strategy: 'S1', version: 1, status: 'active', created_at: '2026-11-14T10:00:00Z', trained_from: '2023-12-27T00:00:00Z', trained_to: '2026-10-13T00:00:00Z', n_samples: 850, cv_auc: 0.6, holdout_auc: 0.63, backtest: null, reason: null, note: null },
  ]

  it('shows ML models with their evidence and says plainly when none is active', async () => {
    mockApi({ ...aiBase, 'GET /ml/models': () => [mlModels[0]] })
    renderAt('/ai')
    expect(await screen.findByText(/S1 v2 · ยังไม่ผ่านเกณฑ์/)).toBeInTheDocument()
    expect(screen.getByText(/AUC holdout 0.616/)).toBeInTheDocument()
    expect(screen.getByText(/-0.087R → -0.058R ต่อเทรด \(132 → 125 เทรด\)/)).toBeInTheDocument()
    expect(screen.getByText(/S_ml = 50 เหมือนเดิม/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Rollback/ })).not.toBeInTheDocument()
  })

  it('rolls an active model back only after the user enters a 2FA code', async () => {
    mockApi({ ...aiBase, 'GET /ml/models': () => mlModels, 'POST /ml/S1/rollback': () => mlModels[1] })
    renderAt('/ai')
    await userEvent.click(await screen.findByRole('button', { name: /Rollback S1/ }))
    expect(calls.some((c) => c.path === '/ml/S1/rollback')).toBe(false) // waits for the code
    const dlg = await screen.findByRole('dialog')
    await userEvent.type(within(dlg).getByLabelText(/TOTP/), '123456')
    await userEvent.click(within(dlg).getByRole('button', { name: /ยืนยัน|Confirm|OK/ }))
    await waitFor(() => expect(calls.find((c) => c.path === '/ml/S1/rollback')?.init?.method).toBe('POST'))
    expect(new Headers(calls.find((c) => c.path === '/ml/S1/rollback')?.init?.headers).get('X-TOTP')).toBe('123456')
  })
})
