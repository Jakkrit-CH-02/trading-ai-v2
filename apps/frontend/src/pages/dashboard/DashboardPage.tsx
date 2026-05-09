import {
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Typography,
  alpha,
  useTheme,
} from "@mui/material";
import {
  TrendingUp as TrendUpIcon,
  TrendingDown as TrendDownIcon,
  AccountBalanceWallet as WalletIcon,
  ShowChart as ChartIcon,
  Layers as PositionsIcon,
  SmartToy as BotIcon,
} from "@mui/icons-material";
import { useQuery } from "@tanstack/react-query";
import {
  getDashboardSummary,
  type BotState,
  type DashboardSummary,
} from "../../api/dashboard";
import OpenPositionsTable from "./OpenPositionsTable";

const REFETCH_MS = 2000;

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

interface WidgetSummaryProps {
  title: string;
  total: string;
  icon: React.ReactNode;
  color: string;
  trend?: { value: number; label: string };
}

function WidgetSummary(props: WidgetSummaryProps) {
  const { title, total, icon, color, trend } = props;
  const theme = useTheme();

  return (
    <Card
      sx={{
        position: "relative",
        overflow: "hidden",
        height: "100%",
      }}
    >
      <CardContent sx={{ position: "relative", zIndex: 1 }}>
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            mb: 3,
          }}
        >
          <Box
            sx={{
              width: 48,
              height: 48,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              borderRadius: "12px",
              background: `linear-gradient(135deg, ${alpha(color, 0.2)} 0%, ${alpha(color, 0.04)} 100%)`,
              color,
            }}
          >
            {icon}
          </Box>
          {trend && (
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 0.5,
                px: 1,
                py: 0.25,
                borderRadius: "8px",
                bgcolor: alpha(
                  trend.value >= 0
                    ? theme.palette.success.main
                    : theme.palette.error.main,
                  0.12,
                ),
                color:
                  trend.value >= 0 ? "success.main" : "error.main",
              }}
            >
              {trend.value >= 0 ? (
                <TrendUpIcon sx={{ fontSize: 16 }} />
              ) : (
                <TrendDownIcon sx={{ fontSize: 16 }} />
              )}
              <Typography variant="caption" sx={{ fontWeight: 700 }}>
                {trend.label}
              </Typography>
            </Box>
          )}
        </Box>

        <Typography variant="h4" sx={{ fontVariantNumeric: "tabular-nums", mb: 0.5 }}>
          {total}
        </Typography>

        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          {title}
        </Typography>
      </CardContent>

      <Box
        sx={{
          position: "absolute",
          top: 0,
          right: 0,
          width: 120,
          height: "100%",
          background: `linear-gradient(135deg, transparent 40%, ${alpha(color, 0.06)} 100%)`,
          pointerEvents: "none",
        }}
      />
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
      <Box
        sx={{
          display: "grid",
          gap: 3,
          gridTemplateColumns: {
            xs: "1fr",
            sm: "repeat(2, 1fr)",
            md: "repeat(4, 1fr)",
          },
        }}
      >
        <WidgetSummary
          title="Equity"
          total={`${renderMoney(data.equity)} USDT`}
          icon={<WalletIcon />}
          color="#00A76F"
        />
        <WidgetSummary
          title="Today P&L"
          total={`${renderSignedMoney(data.pnl_today)} USDT`}
          icon={<ChartIcon />}
          color={pnlNum >= 0 ? "#22C55E" : "#FF5630"}
          trend={
            data.pnl_today != null
              ? {
                  value: pnlNum,
                  label: pnlNum >= 0 ? `+${pnlNum.toFixed(2)}` : pnlNum.toFixed(2),
                }
              : undefined
          }
        />
        <WidgetSummary
          title="Open Positions"
          total={String(data.open_positions.length)}
          icon={<PositionsIcon />}
          color="#00B8D9"
        />
        <Card sx={{ height: "100%" }}>
          <CardContent>
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                mb: 3,
              }}
            >
              <Box
                sx={{
                  width: 48,
                  height: 48,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  borderRadius: "12px",
                  background: (t) =>
                    `linear-gradient(135deg, ${alpha(t.palette.warning.main, 0.2)} 0%, ${alpha(t.palette.warning.main, 0.04)} 100%)`,
                  color: "warning.main",
                }}
              >
                <BotIcon />
              </Box>
            </Box>
            <Box sx={{ mb: 0.5 }}>
              <Chip
                label={data.bot_state.toUpperCase()}
                color={BOT_STATE_COLOR[data.bot_state]}
                size="small"
                sx={{ fontWeight: 700, fontSize: 13 }}
              />
            </Box>
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              Bot State
            </Typography>
          </CardContent>
        </Card>
      </Box>

      <Card>
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            px: 3,
            py: 2.5,
          }}
        >
          <Typography variant="h6">Open Positions</Typography>
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            {data.open_positions.length}{" "}
            {data.open_positions.length === 1 ? "position" : "positions"}
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
    <Box sx={{ p: { xs: 2, md: 3 }, display: "flex", flexDirection: "column", gap: 3 }}>
      <Box>
        <Typography variant="h4">Dashboard</Typography>
        <Typography variant="body2" sx={{ color: "text.secondary", mt: 0.5 }}>
          Hi, Welcome back
        </Typography>
      </Box>

      {summaryQ.isLoading ? (
        <Box
          sx={{
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            py: 8,
          }}
        >
          <CircularProgress />
        </Box>
      ) : summaryQ.isError || !summaryQ.data ? (
        <Box
          sx={{
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            py: 8,
          }}
        >
          <Typography color="error">Failed to load dashboard summary.</Typography>
        </Box>
      ) : (
        <DashboardContent data={summaryQ.data} />
      )}
    </Box>
  );
}
