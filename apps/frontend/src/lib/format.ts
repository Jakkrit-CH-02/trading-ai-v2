export function formatMoney(value: string | number, currency = "USDT"): string {
  const n = typeof value === "string" ? Number(value) : value;
  return `${n.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${currency}`;
}

export function formatPct(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

export function formatTime(ms: number): string {
  return new Date(ms).toLocaleString();
}
