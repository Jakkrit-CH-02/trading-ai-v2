import { Box, Stack, TextField, Typography } from "@mui/material";
import type { Settings } from "../../api/settings";

export interface RiskSettingsFormProps {
  value: Settings;
  errors: Partial<Record<keyof Settings, string>>;
  onChange: (patch: Partial<Settings>) => void;
}

const styles = {
  grid: {
    display: "grid",
    gap: 2,
    gridTemplateColumns: { xs: "1fr", md: "1fr 1fr 1fr" },
  },
  hint: { color: "text.secondary", mb: 1 },
} as const;

export default function RiskSettingsForm(props: RiskSettingsFormProps) {
  const { value, errors, onChange } = props;
  return (
    <Stack spacing={1.5}>
      <Typography variant="body2" sx={styles.hint}>
        Per-trade and per-day risk caps enforced by the backend before any
        order is sent. Decimal fractions (e.g. 0.02 = 2%).
      </Typography>
      <Box sx={styles.grid}>
        <TextField
          label="Max position %"
          value={value.max_position_pct}
          onChange={(e) => onChange({ max_position_pct: e.target.value })}
          error={Boolean(errors.max_position_pct)}
          helperText={errors.max_position_pct ?? "Fraction of equity, e.g. 0.02"}
          inputProps={{ "aria-label": "max position pct" }}
        />
        <TextField
          label="Max daily drawdown %"
          value={value.max_daily_drawdown_pct}
          onChange={(e) =>
            onChange({ max_daily_drawdown_pct: e.target.value })
          }
          error={Boolean(errors.max_daily_drawdown_pct)}
          helperText={
            errors.max_daily_drawdown_pct ?? "Fraction of equity, e.g. 0.05"
          }
          inputProps={{ "aria-label": "max daily drawdown pct" }}
        />
        <TextField
          label="Max slippage (bps)"
          type="number"
          value={value.max_slippage_bps}
          onChange={(e) =>
            onChange({ max_slippage_bps: Number(e.target.value) })
          }
          error={Boolean(errors.max_slippage_bps)}
          helperText={errors.max_slippage_bps ?? "Basis points, e.g. 30"}
          inputProps={{ "aria-label": "max slippage bps", min: 0, max: 10000 }}
        />
      </Box>
    </Stack>
  );
}
