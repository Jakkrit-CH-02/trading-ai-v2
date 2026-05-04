import {
  FormControl,
  FormHelperText,
  InputLabel,
  MenuItem,
  Select,
  Tooltip,
} from "@mui/material";
import type { BotMode } from "../../api/bot";

export interface ModeSelectorProps {
  value: BotMode;
  onChange: (m: BotMode) => void;
  error?: string;
}

const OPTIONS: { value: BotMode; label: string; disabled?: boolean }[] = [
  { value: "backtest", label: "Backtest" },
  { value: "paper", label: "Paper" },
  { value: "live", label: "Live", disabled: true },
];

export default function ModeSelector(props: ModeSelectorProps) {
  const { value, onChange, error } = props;
  return (
    <FormControl fullWidth size="small" error={Boolean(error)}>
      <InputLabel id="bot-mode-label">Mode</InputLabel>
      <Select
        labelId="bot-mode-label"
        label="Mode"
        value={value}
        onChange={(e) => onChange(e.target.value as BotMode)}
      >
        {OPTIONS.map((opt) =>
          opt.disabled ? (
            <Tooltip
              key={opt.value}
              title="Live trading is gated until risk policy and confirmation flow are wired up"
              placement="right"
            >
              <span>
                <MenuItem value={opt.value} disabled>
                  {opt.label}
                </MenuItem>
              </span>
            </Tooltip>
          ) : (
            <MenuItem key={opt.value} value={opt.value}>
              {opt.label}
            </MenuItem>
          ),
        )}
      </Select>
      {error ? <FormHelperText>{error}</FormHelperText> : null}
    </FormControl>
  );
}
