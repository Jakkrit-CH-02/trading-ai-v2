import { AreaSeries, CandlestickSeries, ColorType, createChart, createSeriesMarkers, LineSeries, type IChartApi, type ISeriesApi, type UTCTimestamp } from 'lightweight-charts'
import { useEffect, useRef } from 'react'

export type Candle = { time: number; open: number; high: number; low: number; close: number }
export type BotMarker = { time: number; side: 'buy' | 'sell'; text?: string }

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

export function PriceChart({
  candles,
  mode = 'area',
  markers = [],
  height = 260,
  decimals = 2,
}: {
  candles: Candle[]
  mode?: 'area' | 'candles'
  markers?: BotMarker[]
  height?: number
  decimals?: number
}) {
  const host = useRef<HTMLDivElement>(null)
  const chart = useRef<IChartApi | null>(null)
  const series = useRef<ISeriesApi<'Area'> | ISeriesApi<'Candlestick'> | null>(null)

  useEffect(() => {
    const el = host.current
    if (!el) return
    const c = createChart(el, {
      height,
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: cssVar('--text-secondary'), fontFamily: 'Poppins, sans-serif', attributionLogo: false },
      grid: { vertLines: { visible: false }, horzLines: { color: cssVar('--shadow-dark'), style: 2 } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, timeVisible: true },
      crosshair: { vertLine: { color: cssVar('--text-secondary') }, horzLine: { color: cssVar('--text-secondary') } },
    })
    chart.current = c
    return () => {
      c.remove()
      chart.current = null
      series.current = null
    }
  }, [height])

  useEffect(() => {
    const c = chart.current
    if (!c) return
    if (series.current) c.removeSeries(series.current)
    const fmt = { type: 'price' as const, precision: decimals, minMove: 10 ** -decimals }
    const t = (n: number) => n as UTCTimestamp
    if (mode === 'candles') {
      const s = c.addSeries(CandlestickSeries, {
        upColor: cssVar('--up'),
        downColor: cssVar('--down'),
        wickUpColor: cssVar('--up'),
        wickDownColor: cssVar('--down'),
        borderVisible: false,
        priceFormat: fmt,
      })
      s.setData(candles.map((k) => ({ ...k, time: t(k.time) })))
      series.current = s
    } else {
      const s = c.addSeries(AreaSeries, {
        lineColor: cssVar('--accent'),
        topColor: cssVar('--accent-fill'),
        bottomColor: 'transparent',
        lineWidth: 2,
        priceFormat: fmt,
      })
      s.setData(candles.map((k) => ({ time: t(k.time), value: k.close })))
      series.current = s
    }
    createSeriesMarkers(
      series.current,
      markers.map((m) => ({
        time: t(m.time),
        position: m.side === 'buy' ? ('belowBar' as const) : ('aboveBar' as const),
        shape: m.side === 'buy' ? ('arrowUp' as const) : ('arrowDown' as const),
        color: cssVar('--ink'),
        text: m.text,
      })),
    )
    c.timeScale().fitContent()
  }, [candles, mode, markers, decimals])

  return <div ref={host} className="shadow-inset rounded-panel w-full overflow-hidden p-2" style={{ height }} data-testid="price-chart" />
}

export type LineSeriesInput = { name: string; color: string; data: [number, number][]; area?: boolean }

/** Equity / drawdown style charts: one or more series on a shared time axis. */
export function LineChart({ series, height = 220, percent = false }: { series: LineSeriesInput[]; height?: number; percent?: boolean }) {
  const host = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = host.current
    if (!el) return
    const c = createChart(el, {
      height,
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: cssVar('--text-secondary'), fontFamily: 'Poppins, sans-serif', attributionLogo: false },
      grid: { vertLines: { visible: false }, horzLines: { color: cssVar('--shadow-dark'), style: 2 } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
    })
    const fmt = percent ? { type: 'percent' as const } : { type: 'price' as const, precision: 2, minMove: 0.01 }
    const col = (c: string) => (c.startsWith('var(') ? cssVar(c.slice(4, -1)) : c)
    for (const s of series) {
      const data = s.data.map(([t, v]) => ({ time: t as UTCTimestamp, value: v })).filter((p, i, a) => i === 0 || p.time > a[i - 1].time)
      const line = s.area
        ? c.addSeries(AreaSeries, { lineColor: col(s.color), topColor: cssVar('--accent-fill'), bottomColor: 'transparent', lineWidth: 2, priceFormat: fmt, title: s.name })
        : c.addSeries(LineSeries, { color: col(s.color), lineWidth: 2, priceFormat: fmt, title: s.name })
      line.setData(data)
    }
    c.timeScale().fitContent()
    return () => c.remove()
  }, [series, height, percent])
  return <div ref={host} className="shadow-inset rounded-panel w-full overflow-hidden p-2" style={{ height }} data-testid="line-chart" />
}
