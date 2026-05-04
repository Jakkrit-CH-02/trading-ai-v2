import {
  Box,
  FormControl,
  FormHelperText,
  InputLabel,
  MenuItem,
  Select,
} from "@mui/material";

export type Timeframe = "1m" | "5m" | "15m" | "1h" | "4h" | "1d";

export interface SymbolTimeframePickerProps {
  symbol: string;
  timeframe: Timeframe;
  onSymbolChange: (s: string) => void;
  onTimeframeChange: (t: Timeframe) => void;
  symbolError?: string;
  timeframeError?: string;
}

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];
const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "1h", "4h", "1d"];

export default function SymbolTimeframePicker(
  props: SymbolTimeframePickerProps,
) {
  const {
    symbol,
    timeframe,
    onSymbolChange,
    onTimeframeChange,
    symbolError,
    timeframeError,
  } = props;
  return (
    <Box sx={{ display: "flex", gap: 2 }}>
      <FormControl fullWidth size="small" error={Boolean(symbolError)}>
        <InputLabel id="bot-symbol-label">Symbol</InputLabel>
        <Select
          labelId="bot-symbol-label"
          label="Symbol"
          value={symbol}
          onChange={(e) => onSymbolChange(e.target.value)}
        >
          {SYMBOLS.map((s) => (
            <MenuItem key={s} value={s}>
              {s}
            </MenuItem>
          ))}
        </Select>
        {symbolError ? <FormHelperText>{symbolError}</FormHelperText> : null}
      </FormControl>
      <FormControl
        sx={{ minWidth: 140 }}
        size="small"
        error={Boolean(timeframeError)}
      >
        <InputLabel id="bot-timeframe-label">Timeframe</InputLabel>
        <Select
          labelId="bot-timeframe-label"
          label="Timeframe"
          value={timeframe}
          onChange={(e) => onTimeframeChange(e.target.value as Timeframe)}
        >
          {TIMEFRAMES.map((t) => (
            <MenuItem key={t} value={t}>
              {t}
            </MenuItem>
          ))}
        </Select>
        {timeframeError ? (
          <FormHelperText>{timeframeError}</FormHelperText>
        ) : null}
      </FormControl>
    </Box>
  );
}
