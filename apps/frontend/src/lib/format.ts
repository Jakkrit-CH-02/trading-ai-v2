const moneyFmt = new Intl.NumberFormat(undefined, {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const priceFmt = new Intl.NumberFormat(undefined, {
  minimumFractionDigits: 2,
  maximumFractionDigits: 8,
});

export function formatMoney(value: string | number, currency = "USDT"): string {
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return `— ${currency}`;
  return `${moneyFmt.format(n)} ${currency}`;
}

export function formatPrice(value: string | number): string {
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "—";
  return priceFmt.format(n);
}

export function formatPct(value: number, fractionDigits = 2): string {
  if (!Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(fractionDigits)}%`;
}

export function formatSignedPct(value: number, fractionDigits = 2): string {
  if (!Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(fractionDigits)}%`;
}

export function formatTime(ms: number): string {
  if (!Number.isFinite(ms)) return "—";
  return new Date(ms).toLocaleString();
}

export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return [h, m, sec].map((v) => String(v).padStart(2, "0")).join(":");
}
