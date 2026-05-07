import {
  FormControl,
  FormHelperText,
  InputLabel,
  MenuItem,
  Select,
  Tooltip,
} from "@mui/material";
import type { BotMode } from "../../api/bot";
import { useAuthStore } from "../../stores/authStore";

export interface ModeSelectorProps {
  value: BotMode;
  onChange: (m: BotMode) => void;
  error?: string;
}

const BASE_OPTIONS: { value: BotMode; label: string }[] = [
  { value: "backtest", label: "Backtest" },
  { value: "paper", label: "Paper" },
  { value: "live", label: "Live" },
];

export default function ModeSelector(props: ModeSelectorProps) {
  const { value, onChange, error } = props;
  const role = useAuthStore((s) => s.user?.role);
  const isAdmin = role === "admin";
  return (
    <FormControl fullWidth size="small" error={Boolean(error)}>
      <InputLabel id="bot-mode-label">Mode</InputLabel>
      <Select
        labelId="bot-mode-label"
        label="Mode"
        value={value}
        onChange={(e) => onChange(e.target.value as BotMode)}
      >
        {BASE_OPTIONS.map((opt) => {
          const liveLocked = opt.value === "live" && !isAdmin;
          if (liveLocked) {
            return (
              <Tooltip
                key={opt.value}
                title="Live trading requires admin role"
                placement="right"
              >
                <span>
                  <MenuItem value={opt.value} disabled>
                    {opt.label} (admin only)
                  </MenuItem>
                </span>
              </Tooltip>
            );
          }
          return (
            <MenuItem key={opt.value} value={opt.value}>
              {opt.label}
            </MenuItem>
          );
        })}
      </Select>
      {error ? <FormHelperText>{error}</FormHelperText> : null}
    </FormControl>
  );
}
