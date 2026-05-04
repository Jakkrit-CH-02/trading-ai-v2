import {
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { getRiskSnapshot } from "../../api/risk";
import RiskSummaryCards from "./RiskSummaryCards";
import RiskWarningBanner from "./RiskWarningBanner";
import RiskLimitProgress from "./RiskLimitProgress";
import RiskPositionsTable from "./RiskPositionsTable";

const POLL_MS = 2000;

const styles = {
  root: { p: 3, display: "flex", flexDirection: "column", gap: 3 },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 2,
    flexWrap: "wrap",
  },
  loading: { display: "flex", justifyContent: "center", py: 6 },
} as const;

function stateColor(s: string): "default" | "success" | "warning" | "error" {
  if (s === "running") return "success";
  if (s === "paused") return "warning";
  if (s === "halted") return "error";
  return "default";
}

export default function RiskMonitorPage() {
  const snapQ = useQuery({
    queryKey: ["risk", "snapshot"],
    queryFn: getRiskSnapshot,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
  });

  const snap = snapQ.data;

  return (
    <Box sx={styles.root}>
      <Box sx={styles.header}>
        <Typography variant="h5" sx={{ fontWeight: 600 }}>
          Risk Monitor
        </Typography>
        {snap ? (
          <Chip
            label={snap.state.toUpperCase()}
            color={stateColor(snap.state)}
            sx={{ fontWeight: 700, letterSpacing: 1 }}
          />
        ) : null}
      </Box>

      {snapQ.isLoading || !snap ? (
        <Card>
          <CardContent sx={styles.loading}>
            {snapQ.isError ? (
              <Typography color="error">
                Could not fetch /api/risk/snapshot.
              </Typography>
            ) : (
              <CircularProgress size={24} />
            )}
          </CardContent>
        </Card>
      ) : (
        <Stack spacing={3}>
          <RiskWarningBanner snap={snap} />
          <RiskSummaryCards snap={snap} />
          <RiskLimitProgress snap={snap} />
          <RiskPositionsTable positions={snap.positions} />
        </Stack>
      )}
    </Box>
  );
}
