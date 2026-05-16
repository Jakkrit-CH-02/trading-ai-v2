import { create } from "zustand";
import { z } from "zod";

// Mirrors barDTO from the backend.
export const LiveBarSchema = z.object({
  symbol: z.string(),
  interval: z.string(),
  open_time: z.number().int(),
  close_time: z.number().int(),
  open: z.string(),
  high: z.string(),
  low: z.string(),
  close: z.string(),
  volume: z.string(),
});
export type LiveBar = z.infer<typeof LiveBarSchema>;

const BarFrameSchema = z.object({
  type: z.literal("bar"),
  symbol: z.string(),
  bar: LiveBarSchema,
});

// Module-level generation counter to prevent stale/concurrent reconnect races.
let _generation = 0;

interface MarketStreamState {
  // Latest bar per symbol. Key = symbol string e.g. "BTCUSDT".
  latestBars: Record<string, LiveBar>;
  connected: boolean;
  _ws: WebSocket | null;
  _symbols: string[];
  _reconnectDelayMs: number;

  connect: (symbols: string[], wsBaseUrl: string) => void;
  disconnect: () => void;
}

export const useMarketStreamStore = create<MarketStreamState>((set, get) => ({
  latestBars: {},
  connected: false,
  _ws: null,
  _symbols: [],
  _reconnectDelayMs: 3000,

  connect(symbols, wsBaseUrl) {
    const generation = ++_generation;

    // Clear stale bars from previous symbol set.
    set({ latestBars: {} });

    const existing = get()._ws;
    if (existing) {
      existing.close();
    }

    const url = `${wsBaseUrl}/api/market/stream`;
    const ws = new WebSocket(url);

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "subscribe", symbols }));
      // Reset backoff on successful connection.
      set({ connected: true, _ws: ws, _symbols: symbols, _reconnectDelayMs: 3000 });
    };

    ws.onmessage = (evt) => {
      // Fix 3: guard against non-string frames (e.g. Blob).
      if (typeof evt.data !== "string") return;
      let raw: unknown;
      try {
        raw = JSON.parse(evt.data);
      } catch {
        return;
      }
      const result = BarFrameSchema.safeParse(raw);
      if (!result.success) return;
      const { symbol, bar } = result.data;
      set((s) => ({
        latestBars: { ...s.latestBars, [symbol]: bar },
      }));
    };

    ws.onclose = () => {
      // Compute next exponential backoff before resetting state.
      const currentDelay = get()._reconnectDelayMs;
      const nextDelay = Math.min(currentDelay * 2, 30_000);
      set({ connected: false, _ws: null, _reconnectDelayMs: nextDelay });

      const currentSymbols = get()._symbols;
      if (currentSymbols.length === 0) return;

      setTimeout(() => {
        // If a newer connect() ran during the wait, skip this reconnect.
        if (_generation !== generation) return;
        if (get()._symbols.length > 0) {
          get().connect(currentSymbols, wsBaseUrl);
        }
      }, nextDelay);
    };

    ws.onerror = () => ws.close();
  },

  disconnect() {
    // Capture ws reference first, then clear _symbols BEFORE closing so the
    // onclose reconnect guard sees an empty symbols list and does NOT reconnect.
    const ws = get()._ws;
    set({ _ws: null, _symbols: [], connected: false, _reconnectDelayMs: 3000 });
    if (ws) ws.close();
  },
}));
