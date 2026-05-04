import type { TradeRecord } from "../../api/trades";

const COLUMNS: Array<[string, (t: TradeRecord) => string | number]> = [
  ["id", (t) => t.id],
  ["timestamp_ms", (t) => t.timestamp_ms],
  ["timestamp_iso", (t) => new Date(t.timestamp_ms).toISOString()],
  ["mode", (t) => t.mode],
  ["symbol", (t) => t.symbol],
  ["strategy", (t) => t.strategy],
  ["side", (t) => t.side],
  ["qty", (t) => t.qty],
  ["fill_price", (t) => t.fill_price],
  ["fee", (t) => t.fee],
  ["realized_pl", (t) => t.realized_pl],
  ["cash_after", (t) => t.cash_after],
  ["ai_confidence", (t) => t.ai_confidence],
  ["order_id", (t) => t.order_id],
  ["signal_id", (t) => t.signal_id],
  ["reason", (t) => t.reason],
];

function escape(v: string | number): string {
  const s = String(v);
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

export function tradesToCsv(trades: TradeRecord[]): string {
  const header = COLUMNS.map(([k]) => k).join(",");
  const rows = trades.map((t) =>
    COLUMNS.map(([, get]) => escape(get(t))).join(","),
  );
  return [header, ...rows].join("\n");
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
