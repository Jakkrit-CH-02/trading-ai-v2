/** Number formatting rules from SPEC 10.2: tick-size decimals, K/M above 6 digits. */
export function fmtPrice(v: number, decimals = 2): string {
  return v.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

export function fmtCompact(v: number): string {
  const a = Math.abs(v)
  if (a >= 1e9) return `${(v / 1e9).toFixed(1)}B`
  if (a >= 1e6) return `${(v / 1e6).toFixed(1)}M`
  if (a >= 1e5) return `${(v / 1e3).toFixed(1)}K`
  return v.toLocaleString('en-US', { maximumFractionDigits: 2 })
}

export function decimalsFromTick(tick: number): number {
  return tick >= 1 ? 0 : Math.max(0, Math.round(-Math.log10(tick)))
}
