import { useEffect, useRef } from "react";
import { createChart, CrosshairMode, type IChartApi, type ISeriesApi, type CandlestickData } from "lightweight-charts";
import { Box, Typography } from "@mui/material";
import type { Bar } from "../../api/market";

export interface CandlestickChartProps {
  symbol: string;
  interval: string;
  bars: Bar[];
}

function toChartBar(b: Bar): CandlestickData {
  return {
    time: Math.floor(b.close_time / 1000) as unknown as CandlestickData["time"],
    open: Number(b.open),
    high: Number(b.high),
    low: Number(b.low),
    close: Number(b.close),
  };
}

export default function CandlestickChart(props: CandlestickChartProps) {
  const { symbol, interval, bars } = props;
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = createChart(el, {
      width: el.clientWidth,
      height: 320,
      layout: { background: { color: "#1e1e2e" }, textColor: "#cdd6f4" },
      grid: { vertLines: { color: "#313244" }, horzLines: { color: "#313244" } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#45475a" },
      timeScale: { borderColor: "#45475a", timeVisible: true, secondsVisible: false },
    });

    const series = chart.addCandlestickSeries({
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderVisible: false,
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth });
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series || bars.length === 0) return;
    const data = bars.map(toChartBar).sort((a, b) => (a.time as number) - (b.time as number));
    series.setData(data);
    chartRef.current?.timeScale().fitContent();
  }, [bars]);

  return (
    <Box>
      <Typography variant="subtitle2" sx={{ mb: 1, color: "text.secondary", fontWeight: 600 }}>
        {symbol} · {interval}
      </Typography>
      <Box ref={containerRef} sx={{ width: "100%", borderRadius: 1, overflow: "hidden" }} />
    </Box>
  );
}
