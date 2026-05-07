import { http, HttpResponse } from "msw";

let mockBotState: "idle" | "running" | "paused" | "halted" = "idle";
let mockBotMode: "backtest" | "paper" | "live" = "paper";
let mockBotSymbol = "";

const botStatus = () => ({
  data: {
    state: mockBotState,
    mode: mockBotMode,
    symbol: mockBotSymbol,
    last_signal: { id: "", action: "", symbol: "" },
    last_error: "",
  },
  error: null,
});

// ----- paper portfolio simulator -----------------------------------------
// Drives the paper-trading page. The simulator advances every poll tick:
//  - last close walks via small random step
//  - while bot is running in paper mode, trades flip-flop buy/sell with
//    decaying qty against the walking price
//  - portfolio cash, positions, P&L, equity curve are recomputed accordingly

interface PaperPositionMock {
  symbol: string;
  qty: number;
  avg_entry: number;
  realized_pl: number;
  updated_ms: number;
}

interface PaperTradeMock {
  order_id: string;
  symbol: string;
  side: "buy" | "sell";
  qty: number;
  fill_price: number;
  realized_pl: number;
  cash: number;
  timestamp_ms: number;
}

const INITIAL = 10_000;
const SIM_SYMBOL_DEFAULT = "BTCUSDT";
const TRADE_QTY = 0.01;

let cash = INITIAL;
let position: PaperPositionMock | null = null;
let lastClose = 50_000;
let trades: PaperTradeMock[] = [];
let equityCurve: { timestamp_ms: number; equity: number }[] = [
  { timestamp_ms: Date.now(), equity: INITIAL },
];
let nextTradeAt = 0;

function ulid(): string {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

function unrealized(): number {
  if (!position) return 0;
  return (lastClose - position.avg_entry) * position.qty;
}

function realizedTotal(): number {
  return position?.realized_pl ?? 0;
}

function equity(): number {
  return cash + (position ? position.qty * lastClose : 0);
}

function simulateTick() {
  const now = Date.now();
  // walk price
  const drift = (Math.random() - 0.5) * 50; // +/- 25
  lastClose = Math.max(100, lastClose + drift);

  // generate trades while running in paper mode
  if (mockBotState === "running" && mockBotMode === "paper") {
    if (now >= nextTradeAt) {
      const sym = mockBotSymbol || SIM_SYMBOL_DEFAULT;
      // alternate side based on whether we're flat
      const side: "buy" | "sell" =
        position && position.qty > 0 ? "sell" : "buy";
      const fill =
        side === "buy" ? lastClose * (1 + 0.0001) : lastClose * (1 - 0.0001);
      let realizedDelta = 0;
      if (side === "buy") {
        const cost = TRADE_QTY * fill;
        if (cost <= cash) {
          if (!position || position.qty === 0) {
            position = {
              symbol: sym,
              qty: TRADE_QTY,
              avg_entry: fill,
              realized_pl: position?.realized_pl ?? 0,
              updated_ms: now,
            };
          } else {
            const newQty = position.qty + TRADE_QTY;
            position.avg_entry =
              (position.avg_entry * position.qty + fill * TRADE_QTY) / newQty;
            position.qty = newQty;
            position.updated_ms = now;
          }
          cash -= cost;
        }
      } else if (position && position.qty >= TRADE_QTY) {
        realizedDelta = (fill - position.avg_entry) * TRADE_QTY;
        position.realized_pl += realizedDelta;
        position.qty -= TRADE_QTY;
        position.updated_ms = now;
        cash += TRADE_QTY * fill;
        if (position.qty === 0) position.avg_entry = 0;
      }
      trades.push({
        order_id: ulid(),
        symbol: sym,
        side,
        qty: TRADE_QTY,
        fill_price: fill,
        realized_pl: realizedDelta,
        cash,
        timestamp_ms: now,
      });
      if (trades.length > 200) trades = trades.slice(-200);
      nextTradeAt = now + 4000 + Math.random() * 3000;
    }
  }

  // record equity curve point (cap length)
  equityCurve.push({ timestamp_ms: now, equity: equity() });
  if (equityCurve.length > 240) equityCurve = equityCurve.slice(-240);
}

function fmt(n: number, dp = 2): string {
  return n.toFixed(dp);
}

function portfolioPayload() {
  simulateTick();
  const totalRealized = realizedTotal();
  const wins = trades.filter((t) => t.realized_pl > 0).length;
  const losses = trades.filter((t) => t.realized_pl < 0).length;
  const totalRealizedTrades = wins + losses;
  return {
    data: {
      initial_balance: fmt(INITIAL),
      cash: fmt(cash),
      equity: fmt(equity()),
      realized_pl: fmt(totalRealized),
      unrealized_pl: fmt(unrealized()),
      positions:
        position && position.qty > 0
          ? [
              {
                symbol: position.symbol,
                qty: fmt(position.qty, 6),
                avg_entry: fmt(position.avg_entry),
                unrealized_pl: fmt(unrealized()),
                realized_pl: fmt(position.realized_pl),
                updated_ms: position.updated_ms,
              },
            ]
          : [],
      equity_curve: equityCurve.map((p) => ({
        timestamp_ms: p.timestamp_ms,
        equity: fmt(p.equity),
      })),
      performance: {
        total_trades: trades.length,
        win_trades: wins,
        loss_trades: losses,
        win_rate: totalRealizedTrades > 0 ? wins / totalRealizedTrades : 0,
        total_realized_pl: fmt(totalRealized),
      },
      updated_ms: Date.now(),
    },
    error: null,
  };
}

function tradesPayload() {
  return {
    data: {
      trades: trades
        .slice()
        .reverse()
        .map((t) => ({
          order_id: t.order_id,
          symbol: t.symbol,
          side: t.side,
          qty: fmt(t.qty, 6),
          fill_price: fmt(t.fill_price),
          realized_pl: fmt(t.realized_pl),
          cash: fmt(t.cash),
          timestamp_ms: t.timestamp_ms,
        })),
    },
    error: null,
  };
}

function resetPortfolio() {
  cash = INITIAL;
  position = null;
  trades = [];
  equityCurve = [{ timestamp_ms: Date.now(), equity: INITIAL }];
  nextTradeAt = 0;
}

interface MockUser {
  id: string;
  username: string;
  password: string;
  role: "admin" | "operator" | "viewer";
  created_at: number;
}
const mockUsers: MockUser[] = [
  {
    id: "u_admin",
    username: "admin",
    password: "admin123",
    role: "admin",
    created_at: Date.now(),
  },
];
function publicUser(u: MockUser) {
  return { id: u.id, username: u.username, role: u.role, created_at: u.created_at };
}

export const handlers = [
  http.post("*/api/auth/login", async ({ request }) => {
    const body = (await request.json()) as { username: string; password: string };
    const u = mockUsers.find(
      (x) => x.username === body.username && x.password === body.password,
    );
    if (!u) {
      return HttpResponse.json(
        { data: null, error: { code: "invalid_credentials", message: "invalid username or password" } },
        { status: 401 },
      );
    }
    return HttpResponse.json({
      data: { token: "mock-token-" + u.id, user: publicUser(u) },
      error: null,
    });
  }),
  http.post("*/api/auth/register", async ({ request }) => {
    const body = (await request.json()) as {
      username: string;
      password: string;
      role: MockUser["role"];
    };
    if (mockUsers.some((u) => u.username === body.username)) {
      return HttpResponse.json(
        { data: null, error: { code: "user_exists", message: "username already taken" } },
        { status: 409 },
      );
    }
    const u: MockUser = {
      id: "u_" + ulid(),
      username: body.username,
      password: body.password,
      role: body.role || "viewer",
      created_at: Date.now(),
    };
    mockUsers.push(u);
    return HttpResponse.json({ data: publicUser(u), error: null }, { status: 201 });
  }),
  http.get("*/api/auth/me", ({ request }) => {
    const auth = request.headers.get("Authorization") || "";
    const tok = auth.replace(/^Bearer\s+/i, "");
    const u = mockUsers.find((x) => tok === "mock-token-" + x.id);
    if (!u) {
      return HttpResponse.json(
        { data: null, error: { code: "unauthorized", message: "invalid token" } },
        { status: 401 },
      );
    }
    return HttpResponse.json({ data: publicUser(u), error: null });
  }),
  http.post("*/api/auth/logout", () =>
    HttpResponse.json({ data: { ok: true }, error: null }),
  ),
  http.get("*/api/health", () =>
    HttpResponse.json({ status: "ok", service: "frontend-mock" }),
  ),
  // TODO: remove once backend ships /api/dashboard/summary
  http.get("*/api/dashboard/summary", () =>
    HttpResponse.json({
      data: {
        bot_state: mockBotState,
        equity: null,
        pnl_today: null,
        open_positions: [],
      },
      error: null,
    }),
  ),
  http.get("*/api/bot/status", () => HttpResponse.json(botStatus())),
  http.post("*/api/bot/start", async ({ request }) => {
    const body = (await request.json()) as {
      mode: "backtest" | "paper" | "live";
      symbol: string;
    };
    mockBotState = "running";
    mockBotMode = body.mode;
    mockBotSymbol = body.symbol;
    nextTradeAt = Date.now() + 1000;
    return HttpResponse.json(botStatus());
  }),
  http.post("*/api/bot/stop", () => {
    mockBotState = "idle";
    return HttpResponse.json(botStatus());
  }),
  http.post("*/api/bot/pause", () => {
    mockBotState = "paused";
    return HttpResponse.json(botStatus());
  }),
  http.get("*/api/trades", ({ request }) => {
    simulateTick();
    const url = new URL(request.url);
    const mode = url.searchParams.get("mode") ?? "";
    const symbol = url.searchParams.get("symbol") ?? "";
    const fromMs = Number(url.searchParams.get("from_ms") ?? "0");
    const toMs = Number(url.searchParams.get("to_ms") ?? "0");
    const limit = Number(url.searchParams.get("limit") ?? "100");
    const offset = Number(url.searchParams.get("offset") ?? "0");

    const all = trades
      .slice()
      .reverse()
      .filter((t) => (mode ? mode === "paper" : true))
      .filter((t) => (symbol ? t.symbol === symbol : true))
      .filter((t) => (fromMs ? t.timestamp_ms >= fromMs : true))
      .filter((t) => (toMs ? t.timestamp_ms <= toMs : true));
    const slice = all.slice(offset, offset + limit);

    return HttpResponse.json({
      data: {
        trades: slice.map((t, i) => ({
          id: `${t.order_id}-${i}`,
          mode: "paper",
          symbol: t.symbol,
          side: t.side,
          order_id: t.order_id,
          signal_id: "",
          strategy: "ma_crossover",
          reason: "ma fast crossed slow",
          ai_confidence: "0",
          qty: fmt(t.qty, 6),
          fill_price: fmt(t.fill_price),
          fee: fmt(t.fill_price * t.qty * 0.001),
          realized_pl: fmt(t.realized_pl),
          cash_after: fmt(t.cash),
          timestamp_ms: t.timestamp_ms,
        })),
        total: all.length,
        limit,
        offset,
      },
      error: null,
    });
  }),
  http.get("*/api/risk/snapshot", () => {
    simulateTick();
    const eq = equity();
    const cashV = cash;
    const exposure = eq - cashV;
    const initial = INITIAL;
    const pnl = eq - initial;
    const dd = pnl < 0 && initial > 0 ? Math.abs(pnl) / initial : 0;
    const positions = position && position.qty > 0 ? [position] : [];
    let largestPct = 0;
    const posOut = positions.map((p) => {
      const notional = Math.abs(p.qty * lastClose);
      const pctOf = eq > 0 ? notional / eq : 0;
      if (pctOf > largestPct) largestPct = pctOf;
      return {
        symbol: p.symbol,
        qty: fmt(p.qty, 6),
        avg_entry: fmt(p.avg_entry),
        notional_pct: pctOf.toFixed(6),
        unrealized_pl: fmt((lastClose - p.avg_entry) * p.qty),
        realized_pl: fmt(p.realized_pl),
      };
    });
    return HttpResponse.json({
      data: {
        state: mockBotState,
        max_position_pct: "0.02",
        max_daily_drawdown_pct: "0.05",
        max_slippage_bps: 30,
        equity: fmt(eq),
        initial_equity: fmt(initial),
        cash: fmt(cashV),
        exposure: fmt(exposure),
        exposure_pct: (eq > 0 ? exposure / eq : 0).toFixed(6),
        daily_pnl: fmt(pnl),
        daily_drawdown_pct: dd.toFixed(6),
        open_positions: positions.length,
        largest_position_pct: largestPct.toFixed(6),
        positions: posOut,
        updated_ms: Date.now(),
      },
      error: null,
    });
  }),
  // ----- settings (localStorage-backed so changes persist across reload) ---
  http.get("*/api/settings", () => {
    const raw = localStorage.getItem("mock:settings");
    const s = raw
      ? JSON.parse(raw)
      : {
          user_id: "u_admin",
          default_symbol: "BTCUSDT",
          default_timeframe: "1m",
          default_mode: "paper",
          max_position_pct: "0.02",
          max_daily_drawdown_pct: "0.05",
          max_slippage_bps: 30,
          notify_email: false,
          notify_webhook_url: "",
          updated_at: Date.now(),
        };
    return HttpResponse.json({ data: s, error: null });
  }),
  http.put("*/api/settings", async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    const updated = { ...body, updated_at: Date.now() };
    localStorage.setItem("mock:settings", JSON.stringify(updated));
    return HttpResponse.json({ data: updated, error: null });
  }),
  http.get("*/api/settings/binance-key/status", () => {
    const raw = localStorage.getItem("mock:binance-key");
    const s = raw
      ? JSON.parse(raw)
      : {
          configured: false,
          masked_key: "",
          permissions: { read: false, spot_trade: false, withdraw: false },
          testnet: true,
          last_checked_ms: 0,
        };
    return HttpResponse.json({ data: s, error: null });
  }),
  http.post("*/api/settings/binance-key/test", () => {
    const s = {
      configured: true,
      masked_key: "abcd••••••••wxyz",
      permissions: { read: true, spot_trade: true, withdraw: false },
      testnet: true,
      last_checked_ms: Date.now(),
    };
    localStorage.setItem("mock:binance-key", JSON.stringify(s));
    return HttpResponse.json({ data: s, error: null });
  }),
  http.get("*/api/paper/portfolio", () =>
    HttpResponse.json(portfolioPayload()),
  ),
  http.get("*/api/paper/trades", () => HttpResponse.json(tradesPayload())),
  http.post("*/api/paper/reset", () => {
    resetPortfolio();
    return HttpResponse.json(portfolioPayload());
  }),
  http.get("*/api/alerts", () => {
    if (mockAlerts.length === 0) seedMockAlerts();
    maybeAppendMockAlert();
    return HttpResponse.json({ data: mockAlerts, error: null });
  }),
  http.post("*/api/alerts/:id/ack", ({ params }) => {
    const id = String(params.id);
    const item = mockAlerts.find((a) => a.id === id);
    if (!item) {
      return HttpResponse.json(
        { data: null, error: { code: "not_found", message: "alert not found" } },
        { status: 404 },
      );
    }
    item.read = true;
    return HttpResponse.json({
      data: { id, status: "acked" },
      error: null,
    });
  }),
];

interface MockAlert {
  id: string;
  type: string;
  severity: "info" | "warning" | "critical";
  message: string;
  entity: string;
  read: boolean;
  created_at: number;
}

const mockAlerts: MockAlert[] = [];

function seedMockAlerts() {
  const now = Date.now();
  mockAlerts.push(
    {
      id: "alrt_seed_info",
      type: "order_rejection",
      severity: "info",
      message: "Order rejected: insufficient balance",
      entity: "ord_001",
      read: true,
      created_at: now - 3_600_000,
    },
    {
      id: "alrt_seed_warn",
      type: "slippage_exceeded",
      severity: "warning",
      message: "Slippage 42 bps exceeded threshold 30",
      entity: "BTCUSDT",
      read: false,
      created_at: now - 600_000,
    },
    {
      id: "alrt_seed_crit",
      type: "kill_triggered",
      severity: "critical",
      message: "Kill switch triggered — all positions flattened",
      entity: "system",
      read: false,
      created_at: now - 60_000,
    },
  );
}

let lastAppend = 0;
function maybeAppendMockAlert() {
  const now = Date.now();
  if (now - lastAppend < 12_000) return;
  lastAppend = now;
  if (mockAlerts.length >= 10) return;
  mockAlerts.unshift({
    id: `alrt_${now}`,
    type: "drawdown_breach",
    severity: "warning",
    message: `Daily drawdown approaching cap (${new Date(now).toLocaleTimeString()})`,
    entity: "equity",
    read: false,
    created_at: now,
  });
}
