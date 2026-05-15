import { useEffect, useRef } from "react";
import { createChart, CrosshairMode, type IChartApi, type ISeriesApi, type CandlestickData, type UTCTimestamp } from "lightweight-charts";
import { Box, Typography, useTheme } from "@mui/material";
import type { Bar } from "../../api/market";

export interface CandlestickChartProps {
  symbol: string;
  interval: string;
  bars: Bar[];
}

const CHART_HEIGHT = 320;

// lightweight-charts requires JS numbers; string decimals are safe to convert here (display only)
function toChartBar(b: Bar): CandlestickData {
  return {
    time: Math.floor(b.close_time / 1000) as UTCTimestamp,
    open: Number(b.open),
    high: Number(b.high),
    low: Number(b.low),
    close: Number(b.close),
  };
}

export default function CandlestickChart(props: CandlestickChartProps) {
  const { symbol, interval, bars } = props;
  const theme = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = createChart(el, {
      width: el.clientWidth,
      height: CHART_HEIGHT,
      layout: {
        background: { color: theme.palette.background.paper },
        textColor: theme.palette.text.primary,
      },
      grid: {
        vertLines: { color: theme.palette.divider },
        horzLines: { color: theme.palette.divider },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: theme.palette.divider },
      timeScale: {
        borderColor: theme.palette.divider,
        timeVisible: true,
        secondsVisible: false,
      },
    });

    const series = chart.addCandlestickSeries({
      upColor: theme.palette.success.main,
      downColor: theme.palette.error.main,
      borderVisible: false,
      wickUpColor: theme.palette.success.main,
      wickDownColor: theme.palette.error.main,
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
  }, [theme.palette.mode]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    const data = bars.length === 0
      ? []
      : bars.map(toChartBar).sort((a, b) => (a.time as number) - (b.time as number));
    series.setData(data);
    if (data.length > 0) chartRef.current?.timeScale().fitContent();
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
