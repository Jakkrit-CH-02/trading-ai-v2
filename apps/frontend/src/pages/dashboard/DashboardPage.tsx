import {
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import {
  getDashboardSummary,
  type BotState,
  type DashboardSummary,
} from "../../api/dashboard";
import OpenPositionsTable from "./OpenPositionsTable";

const REFETCH_MS = 2000;

const styles = {
  root: { p: 3, display: "flex", flexDirection: "column", gap: 3 },
  kpiGrid: {
    display: "grid",
    gap: 2,
    gridTemplateColumns: {
      xs: "1fr",
      sm: "repeat(2, 1fr)",
      md: "repeat(4, 1fr)",
    },
  },
  kpiCard: { height: "100%" },
  kpiLabel: {
    color: "text.secondary",
    fontSize: 12,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  kpiValue: { fontVariantNumeric: "tabular-nums", mt: 1 },
  kpiHint: { color: "text.disabled", fontSize: 11, mt: 0.5 },
  centerCell: {
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    py: 6,
  },
  pnl: (n: number) => ({
    fontVariantNumeric: "tabular-nums",
    color: n > 0 ? "success.main" : n < 0 ? "error.main" : "text.primary",
  }),
} as const;

const BOT_STATE_COLOR: Record<
  BotState,
  "default" | "success" | "warning" | "error"
> = {
  idle: "default",
  running: "success",
  paused: "warning",
  halted: "error",
  error: "error",
};

interface KpiCardProps {
  label: string;
  value: React.ReactNode;
  hint?: string;
  valueSx?: object;
}

function KpiCard(props: KpiCardProps) {
  const { label, value, hint, valueSx } = props;
  return (
    <Card sx={styles.kpiCard}>
      <CardContent>
        <Typography sx={styles.kpiLabel}>{label}</Typography>
        <Typography variant="h5" sx={{ ...styles.kpiValue, ...valueSx }}>
          {value}
        </Typography>
        {hint ? <Typography sx={styles.kpiHint}>{hint}</Typography> : null}
      </CardContent>
    </Card>
  );
}

function renderMoney(value: string | null): string {
  if (value == null) return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  return n.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function renderSignedMoney(value: string | null): string {
  if (value == null) return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function DashboardContent({ data }: { data: DashboardSummary }) {
  const pnlNum = data.pnl_today == null ? 0 : Number(data.pnl_today);

  return (
    <>
      <Box sx={styles.kpiGrid}>
        <KpiCard
          label="Equity"
          value={renderMoney(data.equity)}
          hint={
            data.equity == null
              ? "Available once paper trading is wired up"
              : "USDT"
          }
        />
        <KpiCard
          label="Today P&L"
          value={renderSignedMoney(data.pnl_today)}
          hint={data.pnl_today == null ? "—" : "USDT"}
          valueSx={data.pnl_today == null ? {} : styles.pnl(pnlNum)}
        />
        <KpiCard
          label="Open Positions"
          value={data.open_positions.length}
          hint={data.open_positions.length === 1 ? "position" : "positions"}
        />
        <KpiCard
          label="Bot State"
          value={
            <Chip
              label={data.bot_state.toUpperCase()}
              color={BOT_STATE_COLOR[data.bot_state]}
              size="small"
              sx={{ fontWeight: 600 }}
            />
          }
        />
      </Box>

      <Card>
        <Box sx={{ px: 2, py: 1.5 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
            Open Positions
          </Typography>
        </Box>
        <OpenPositionsTable positions={data.open_positions} />
      </Card>
    </>
  );
}

export default function DashboardPage() {
  const summaryQ = useQuery({
    queryKey: ["dashboard", "summary"],
    queryFn: getDashboardSummary,
    refetchInterval: REFETCH_MS,
  });

  return (
    <Box sx={styles.root}>
      <Typography variant="h5">Dashboard</Typography>

      {summaryQ.isLoading ? (
        <Box sx={styles.centerCell}>
          <CircularProgress />
        </Box>
      ) : summaryQ.isError || !summaryQ.data ? (
        <Box sx={styles.centerCell}>
          <Typography color="error">
            Failed to load dashboard summary.
          </Typography>
        </Box>
      ) : (
        <DashboardContent data={summaryQ.data} />
      )}
    </Box>
  );
}
