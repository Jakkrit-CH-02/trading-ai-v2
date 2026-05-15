import {
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  FormHelperText,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
import type { RunMultiBacktestInput } from "../../api/backtest";

const STRATEGIES = [
  { value: "ma_cross", label: "MA Crossover" },
  { value: "ma_rsi_filter", label: "MA + RSI Filter" },
  { value: "rsi", label: "RSI" },
  { value: "ai", label: "AI Model" },
];

const INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"];

const SYMBOL_PRESETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];

const TIMEFRAME_PRESETS: Record<
  string,
  { fast: number; slow: number; rsiPeriod: number }
> = {
  "1m":  { fast: 3,  slow: 8,  rsiPeriod: 7  },
  "5m":  { fast: 5,  slow: 13, rsiPeriod: 10 },
  "15m": { fast: 8,  slow: 21, rsiPeriod: 14 },
  "1h":  { fast: 9,  slow: 21, rsiPeriod: 14 },
  "4h":  { fast: 9,  slow: 21, rsiPeriod: 14 },
  "1d":  { fast: 12, slow: 26, rsiPeriod: 14 },
};

export interface BacktestRunFormValues {
  symbols: string[];
  interval: string;
  strategy_name: string;
  initial_cash: string;
  position_fraction: string;
  stop_loss_pct: string;
  trail_activation_pct: string;
  trail_pct: string;
  from: string;
  to: string;
  limit: string;
  fast_period: string;
  slow_period: string;
  rsi_period: string;
  rsi_buy_max: string;
  rsi_sell_min: string;
}

export interface BacktestRunFormProps {
  onSubmit: (input: RunMultiBacktestInput) => void;
  pending: boolean;
}

const styles = {
  grid: {
    display: "grid",
    gap: 2,
    gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", md: "repeat(3, 1fr)" },
  },
} as const;

export default function BacktestRunForm(props: BacktestRunFormProps) {
  const { onSubmit, pending } = props;
  const { register, handleSubmit, watch, control, setValue } =
    useForm<BacktestRunFormValues>({
      defaultValues: {
        symbols: ["BTCUSDT"],
        interval: "4h",
        strategy_name: "ma_rsi_filter",
        initial_cash: "10000",
        position_fraction: "0.1",
        stop_loss_pct: "0.08",
        trail_activation_pct: "0.03",
        trail_pct: "0.02",
        from: "",
        to: "",
        limit: "",
        fast_period: "9",
        slow_period: "21",
        rsi_period: "14",
        rsi_buy_max: "60",
        rsi_sell_min: "40",
      },
    });

  const strategy_name = watch("strategy_name");
  const interval = watch("interval");
  const from = watch("from");
  const to = watch("to");

  // Auto-populate EMA/RSI period fields when strategy + interval change.
  useEffect(() => {
    if (strategy_name !== "ma_rsi_filter") return;
    const preset = TIMEFRAME_PRESETS[interval];
    if (!preset) return;
    setValue("fast_period", String(preset.fast));
    setValue("slow_period", String(preset.slow));
    setValue("rsi_period", String(preset.rsiPeriod));
  }, [interval, strategy_name, setValue]);

  const isMACross = strategy_name === "ma_cross";
  const isMARSI = strategy_name === "ma_rsi_filter";

  const submit = handleSubmit((v) => {
    const fromMs = v.from ? Date.parse(v.from) : 0;
    const toMs = v.to ? Date.parse(v.to) : Date.now();
    const params: Record<string, string> = {};
    if (isMACross) {
      if (v.fast_period) params.fast = v.fast_period;
      if (v.slow_period) params.slow = v.slow_period;
    }
    if (isMARSI) {
      if (v.fast_period) params.fast = v.fast_period;
      if (v.slow_period) params.slow = v.slow_period;
      if (v.rsi_period) params.rsi_period = v.rsi_period;
      if (v.rsi_buy_max) params.rsi_buy_max = v.rsi_buy_max;
      if (v.rsi_sell_min) params.rsi_sell_min = v.rsi_sell_min;
    }
    const derivedLimit = estimateLimit(v.interval, fromMs, toMs);
    const input: RunMultiBacktestInput = {
      symbols: v.symbols.map((s) => s.trim().toUpperCase()).filter(Boolean),
      interval: v.interval,
      strategy_name: v.strategy_name,
      strategy_params: params,
      initial_cash: v.initial_cash,
      position_fraction: v.position_fraction,
      stop_loss_pct: v.stop_loss_pct,
      trail_activation_pct: v.trail_activation_pct || undefined,
      trail_pct: v.trail_pct || undefined,
      from_ms: Number.isFinite(fromMs) && fromMs > 0 ? fromMs : undefined,
      to_ms:
        Number.isFinite(toMs) && toMs > 0 && v.from ? toMs : undefined,
      limit: v.limit ? Number(v.limit) : derivedLimit,
    };
    onSubmit(input);
  });

  const estimatedBars = estimateLimit(
    interval,
    from ? Date.parse(from) : 0,
    to ? Date.parse(to) : Date.now(),
  );
  const isLongRange =
    Boolean(from) && estimatedBars !== undefined && estimatedBars > 5000;

  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
          Launch Backtest
        </Typography>
        <Box component="form" onSubmit={submit}>
          <Box sx={styles.grid}>
            <Controller
              name="symbols"
              control={control}
              render={({ field }) => (
                <Autocomplete
                  multiple
                  freeSolo
                  options={SYMBOL_PRESETS}
                  value={field.value}
                  onChange={(_, v) => field.onChange(v)}
                  renderTags={(value, getTagProps) =>
                    value.map((option, index) => (
                      <Chip
                        {...getTagProps({ index })}
                        key={option}
                        label={option}
                        size="small"
                      />
                    ))
                  }
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Symbol(s)"
                      size="small"
                      placeholder={field.value.length === 0 ? "BTCUSDT" : ""}
                    />
                  )}
                />
              )}
            />
            <TextField
              label="Interval"
              size="small"
              select
              {...register("interval")}
            >
              {INTERVALS.map((i) => (
                <MenuItem key={i} value={i}>
                  {i}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Strategy"
              size="small"
              select
              {...register("strategy_name")}
            >
              {STRATEGIES.map((s) => (
                <MenuItem key={s.value} value={s.value}>
                  {s.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="From (UTC)"
              size="small"
              type="datetime-local"
              InputLabelProps={{ shrink: true }}
              {...register("from")}
            />
            <TextField
              label="To (UTC)"
              size="small"
              type="datetime-local"
              InputLabelProps={{ shrink: true }}
              {...register("to")}
            />
            <TextField
              label="Bar limit"
              size="small"
              type="number"
              {...register("limit")}
            />
            <TextField
              label="Initial cash"
              size="small"
              {...register("initial_cash")}
            />
            <TextField
              label="Position fraction (0..1)"
              size="small"
              {...register("position_fraction")}
            />
            <TextField
              label="Stop loss pct (0..1)"
              size="small"
              {...register("stop_loss_pct")}
            />
            <TextField
              label="Trail Activation % (0..1)"
              size="small"
              {...register("trail_activation_pct")}
            />
            <TextField
              label="Trail Distance % (0..1)"
              size="small"
              {...register("trail_pct")}
            />
            {isMACross || isMARSI ? (
              <>
                <TextField
                  label="Fast period"
                  size="small"
                  type="number"
                  {...register("fast_period")}
                />
                <TextField
                  label="Slow period"
                  size="small"
                  type="number"
                  {...register("slow_period")}
                />
              </>
            ) : null}
            {isMARSI ? (
              <>
                <TextField
                  label="RSI Period"
                  size="small"
                  type="number"
                  {...register("rsi_period")}
                />
                <TextField
                  label="RSI Buy Max (0..100)"
                  size="small"
                  type="number"
                  {...register("rsi_buy_max")}
                />
                <TextField
                  label="RSI Sell Min (0..100)"
                  size="small"
                  type="number"
                  {...register("rsi_sell_min")}
                />
              </>
            ) : null}
          </Box>
          <FormHelperText sx={{ mt: 1 }}>
            Leave `Bar limit` blank to auto-size from the selected range. For
            quick visual verification, use `1h` or `4h` on long ranges; `1m`
            over months can still be slow.
          </FormHelperText>
          {isLongRange ? (
            <FormHelperText sx={{ mt: 0.5 }} error>
              This range is about {estimatedBars?.toLocaleString()} bars at `
              {interval}`. The app will cap the run to 10,000 bars unless you
              narrow the range or increase the interval.
            </FormHelperText>
          ) : null}
          <Stack direction="row" spacing={2} sx={{ mt: 3 }}>
            <Button
              type="submit"
              variant="contained"
              startIcon={
                pending ? (
                  <CircularProgress size={16} color="inherit" />
                ) : (
                  <PlayArrowIcon />
                )
              }
              disabled={pending}
            >
              {pending ? "Running…" : "Run Backtest"}
            </Button>
          </Stack>
        </Box>
      </CardContent>
    </Card>
  );
}

function estimateLimit(
  interval: string,
  fromMs: number,
  toMs: number,
): number | undefined {
  if (
    !Number.isFinite(fromMs) ||
    fromMs <= 0 ||
    !Number.isFinite(toMs) ||
    toMs <= fromMs
  ) {
    return undefined;
  }
  const stepMs = intervalToMs(interval);
  if (!stepMs) return undefined;
  const bars = Math.floor((toMs - fromMs) / stepMs) + 1;
  return Math.min(Math.max(bars, 1), 10000);
}

function intervalToMs(interval: string): number | undefined {
  const value = Number(interval.slice(0, -1));
  if (!Number.isFinite(value) || value <= 0) return undefined;
  const unit = interval.slice(-1);
  switch (unit) {
    case "m": return value * 60_000;
    case "h": return value * 3_600_000;
    case "d": return value * 86_400_000;
    default:  return undefined;
  }
}
