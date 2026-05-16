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

interface MarketStreamState {
  // Latest bar per symbol. Key = symbol string e.g. "BTCUSDT".
  latestBars: Record<string, LiveBar>;
  connected: boolean;
  _ws: WebSocket | null;
  _symbols: string[];

  connect: (symbols: string[], wsBaseUrl: string) => void;
  disconnect: () => void;
}

export const useMarketStreamStore = create<MarketStreamState>((set, get) => ({
  latestBars: {},
  connected: false,
  _ws: null,
  _symbols: [],

  connect(symbols, wsBaseUrl) {
    const existing = get()._ws;
    if (existing) {
      existing.close();
    }

    const url = `${wsBaseUrl}/api/market/stream`;
    const ws = new WebSocket(url);

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "subscribe", symbols }));
      set({ connected: true, _ws: ws, _symbols: symbols });
    };

    ws.onmessage = (evt) => {
      let raw: unknown;
      try {
        raw = JSON.parse(evt.data as string);
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
      set({ connected: false, _ws: null });
      // Reconnect after 3s if we still want this connection.
      const currentSymbols = get()._symbols;
      if (currentSymbols.length > 0) {
        setTimeout(() => {
          if (get()._symbols.length > 0) {
            get().connect(currentSymbols, wsBaseUrl);
          }
        }, 3000);
      }
    };

    ws.onerror = () => ws.close();
  },

  disconnect() {
    // Capture ws reference first, then clear _symbols BEFORE closing so the
    // onclose reconnect guard sees an empty symbols list and does NOT reconnect.
    const ws = get()._ws;
    set({ _ws: null, _symbols: [], connected: false });
    if (ws) ws.close();
  },
}));
