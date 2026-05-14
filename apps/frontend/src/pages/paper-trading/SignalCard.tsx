import { Box, Card, CardContent, Chip, Divider, Typography } from "@mui/material";
import type { BotSignal } from "../../api/bot";

const ACTION_COLOR: Record<string, "success" | "error" | "default"> = {
  buy: "success",
  sell: "error",
  hold: "default",
};

const styles = {
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(2, 1fr)",
    gap: 2,
    mt: 2,
  },
  cell: { display: "flex", flexDirection: "column", gap: 0.5 },
  label: { fontSize: 11, fontWeight: 600, letterSpacing: 0.8, color: "text.disabled", textTransform: "uppercase" },
  value: { fontSize: 14, fontWeight: 500 },
  reason: { fontSize: 13, color: "text.secondary", fontStyle: "italic", mt: 1 },
} as const;

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box sx={styles.cell}>
      <Typography sx={styles.label}>{label}</Typography>
      <Typography sx={styles.value}>{children}</Typography>
    </Box>
  );
}

function formatStrength(s: string | undefined): string {
  if (!s) return "—";
  const n = parseFloat(s);
  if (isNaN(n)) return s;
  return `${(n * 100).toFixed(1)}%`;
}

function formatTime(ms: number | undefined): string {
  if (!ms) return "—";
  return new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

interface SignalCardProps {
  signal: BotSignal;
}

export default function SignalCard({ signal }: SignalCardProps) {
  const action = signal.action?.toLowerCase() ?? "";
  const hasSignal = action !== "" && action !== "hold";

  return (
    <Card>
      <CardContent>
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
            Last Signal
          </Typography>
          {action ? (
            <Chip
              label={action.toUpperCase()}
              color={ACTION_COLOR[action] ?? "default"}
              size="small"
              sx={{ fontWeight: 700, fontSize: 13, px: 0.5 }}
            />
          ) : (
            <Chip label="NONE YET" size="small" variant="outlined" />
          )}
        </Box>

        {!hasSignal && !signal.id ? (
          <Typography sx={{ color: "text.secondary", mt: 1.5, fontSize: 14 }}>
            No signal received yet. The strategy will emit one after the next closed candle.
          </Typography>
        ) : (
          <>
            <Divider sx={{ mt: 1.5 }} />
            <Box sx={styles.grid}>
              <Field label="Symbol">{signal.symbol || "—"}</Field>
              <Field label="Strategy">{signal.strategy || "—"}</Field>
              <Field label="Strength">{formatStrength(signal.strength)}</Field>
              <Field label="Time">{formatTime(signal.created_ms)}</Field>
            </Box>
            {signal.reason ? (
              <Typography sx={styles.reason}>"{signal.reason}"</Typography>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}
