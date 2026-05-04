import {
  FormControl,
  FormHelperText,
  InputLabel,
  MenuItem,
  Select,
} from "@mui/material";

export type StrategyId = "ma_cross" | "rsi" | "ai";

export interface StrategyPickerProps {
  value: StrategyId;
  onChange: (s: StrategyId) => void;
  error?: string;
}

const OPTIONS: { value: StrategyId; label: string }[] = [
  { value: "ma_cross", label: "MA Crossover" },
  { value: "rsi", label: "RSI" },
  { value: "ai", label: "AI Model" },
];

export default function StrategyPicker(props: StrategyPickerProps) {
  const { value, onChange, error } = props;
  return (
    <FormControl fullWidth size="small" error={Boolean(error)}>
      <InputLabel id="bot-strategy-label">Strategy</InputLabel>
      <Select
        labelId="bot-strategy-label"
        label="Strategy"
        value={value}
        onChange={(e) => onChange(e.target.value as StrategyId)}
      >
        {OPTIONS.map((opt) => (
          <MenuItem key={opt.value} value={opt.value}>
            {opt.label}
          </MenuItem>
        ))}
      </Select>
      {error ? <FormHelperText>{error}</FormHelperText> : null}
    </FormControl>
  );
}
