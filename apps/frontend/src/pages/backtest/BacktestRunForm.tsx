import {
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import { useForm } from "react-hook-form";
import type { RunBacktestInput } from "../../api/backtest";

const STRATEGIES = [
  { value: "ma_cross", label: "MA Crossover" },
  { value: "rsi", label: "RSI" },
  { value: "ai", label: "AI Model" },
];

const INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"];

export interface BacktestRunFormValues {
  symbol: string;
  interval: string;
  strategy_name: string;
  initial_cash: string;
  position_fraction: string;
  stop_loss_pct: string;
  from: string;
  to: string;
  limit: string;
  fast_period: string;
  slow_period: string;
}

export interface BacktestRunFormProps {
  onSubmit: (input: RunBacktestInput) => void;
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
  const { register, handleSubmit, watch } = useForm<BacktestRunFormValues>({
    defaultValues: {
      symbol: "BTCUSDT",
      interval: "1m",
      strategy_name: "ma_cross",
      initial_cash: "10000",
      position_fraction: "0.5",
      stop_loss_pct: "0.05",
      from: "",
      to: "",
      limit: "1000",
      fast_period: "9",
      slow_period: "21",
    },
  });
  const strategy = watch("strategy_name");

  const submit = handleSubmit((v) => {
    const fromMs = v.from ? Date.parse(v.from) : 0;
    const toMs = v.to ? Date.parse(v.to) : 0;
    const params: Record<string, string> = {};
    if (v.strategy_name === "ma_cross") {
      if (v.fast_period) params.fast_period = v.fast_period;
      if (v.slow_period) params.slow_period = v.slow_period;
    }
    const input: RunBacktestInput = {
      symbol: v.symbol.trim().toUpperCase(),
      interval: v.interval,
      strategy_name: v.strategy_name,
      strategy_params: params,
      initial_cash: v.initial_cash,
      position_fraction: v.position_fraction,
      stop_loss_pct: v.stop_loss_pct,
      from_ms: Number.isFinite(fromMs) && fromMs > 0 ? fromMs : undefined,
      to_ms: Number.isFinite(toMs) && toMs > 0 ? toMs : undefined,
      limit: v.limit ? Number(v.limit) : undefined,
    };
    onSubmit(input);
  });

  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
          Launch Backtest
        </Typography>
        <Box component="form" onSubmit={submit}>
          <Box sx={styles.grid}>
            <TextField
              label="Symbol"
              size="small"
              {...register("symbol", { required: true })}
            />
            <TextField
              label="Interval"
              size="small"
              select
              defaultValue="1m"
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
              defaultValue="ma_cross"
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
            {strategy === "ma_cross" ? (
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
          </Box>
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
