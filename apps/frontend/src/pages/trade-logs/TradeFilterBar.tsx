import {
  Box,
  Button,
  MenuItem,
  TextField,
} from "@mui/material";

export interface TradeFilters {
  mode: "" | "backtest" | "paper" | "live";
  symbol: string;
  strategy: string;
  fromDate: string;
  toDate: string;
}

export interface TradeFilterBarProps {
  value: TradeFilters;
  onChange: (next: TradeFilters) => void;
  onReset: () => void;
}

const styles = {
  root: {
    display: "grid",
    gap: 2,
    p: 2,
    gridTemplateColumns: {
      xs: "1fr",
      sm: "1fr 1fr",
      md: "repeat(5, 1fr) auto",
    },
    alignItems: "center",
    bgcolor: "background.paper",
    borderRadius: 1,
  },
} as const;

export default function TradeFilterBar(props: TradeFilterBarProps) {
  const { value, onChange, onReset } = props;
  const set = <K extends keyof TradeFilters>(k: K, v: TradeFilters[K]) =>
    onChange({ ...value, [k]: v });

  return (
    <Box sx={styles.root}>
      <TextField
        select
        label="Mode"
        size="small"
        value={value.mode}
        onChange={(e) =>
          set("mode", e.target.value as TradeFilters["mode"])
        }
      >
        <MenuItem value="">All</MenuItem>
        <MenuItem value="paper">Paper</MenuItem>
        <MenuItem value="live">Live</MenuItem>
        <MenuItem value="backtest">Backtest</MenuItem>
      </TextField>
      <TextField
        label="Symbol"
        size="small"
        placeholder="BTCUSDT"
        value={value.symbol}
        onChange={(e) => set("symbol", e.target.value.toUpperCase())}
      />
      <TextField
        label="Strategy"
        size="small"
        value={value.strategy}
        onChange={(e) => set("strategy", e.target.value)}
      />
      <TextField
        label="From"
        size="small"
        type="date"
        InputLabelProps={{ shrink: true }}
        value={value.fromDate}
        onChange={(e) => set("fromDate", e.target.value)}
      />
      <TextField
        label="To"
        size="small"
        type="date"
        InputLabelProps={{ shrink: true }}
        value={value.toDate}
        onChange={(e) => set("toDate", e.target.value)}
      />
      <Button variant="outlined" size="small" onClick={onReset}>
        Reset
      </Button>
    </Box>
  );
}
