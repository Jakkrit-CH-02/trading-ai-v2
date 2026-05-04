import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Stack,
  TablePagination,
  Typography,
} from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listTrades, type TradeListQuery } from "../../api/trades";
import TradeFilterBar, { type TradeFilters } from "./TradeFilterBar";
import TradeTable from "./TradeTable";
import { downloadCsv, tradesToCsv } from "./csv";

const ROWS_PER_PAGE_OPTIONS = [25, 50, 100];

const styles = {
  root: { p: 3, display: "flex", flexDirection: "column", gap: 2 },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 2,
    flexWrap: "wrap",
  },
  card: { overflow: "hidden" },
  tableWrap: { overflowX: "auto" },
} as const;

const EMPTY_FILTERS: TradeFilters = {
  mode: "",
  symbol: "",
  strategy: "",
  fromDate: "",
  toDate: "",
};

function dateToFromMs(s: string): number | undefined {
  if (!s) return undefined;
  const t = new Date(`${s}T00:00:00Z`).getTime();
  return Number.isFinite(t) ? t : undefined;
}

function dateToToMs(s: string): number | undefined {
  if (!s) return undefined;
  const t = new Date(`${s}T23:59:59.999Z`).getTime();
  return Number.isFinite(t) ? t : undefined;
}

export default function TradeLogsPage() {
  const [filters, setFilters] = useState<TradeFilters>(EMPTY_FILTERS);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);

  const query: TradeListQuery = useMemo(
    () => ({
      mode: filters.mode,
      symbol: filters.symbol.trim(),
      strategy: filters.strategy.trim(),
      from_ms: dateToFromMs(filters.fromDate),
      to_ms: dateToToMs(filters.toDate),
      limit: rowsPerPage,
      offset: page * rowsPerPage,
    }),
    [filters, page, rowsPerPage],
  );

  const tradesQ = useQuery({
    queryKey: ["trades", "list", query],
    queryFn: () => listTrades(query),
    placeholderData: (prev) => prev,
    refetchInterval: 5000,
  });

  const trades = tradesQ.data?.trades ?? [];
  const total = tradesQ.data?.total ?? 0;
  const errorMsg =
    tradesQ.isError && tradesQ.error
      ? tradesQ.error instanceof Error
        ? tradesQ.error.message
        : "Failed to load trades."
      : null;

  const handleFiltersChange = (next: TradeFilters) => {
    setFilters(next);
    setPage(0);
  };

  const handleReset = () => {
    setFilters(EMPTY_FILTERS);
    setPage(0);
  };

  const handleExport = () => {
    if (trades.length === 0) return;
    const csv = tradesToCsv(trades);
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    downloadCsv(`trades-${stamp}.csv`, csv);
  };

  return (
    <Box sx={styles.root}>
      <Box sx={styles.header}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 600 }}>
            Trade Logs
          </Typography>
          <Typography sx={{ color: "text.secondary", fontSize: 14 }}>
            Browse order fills across paper, live, and backtest modes.
          </Typography>
        </Box>
        <Button
          variant="outlined"
          size="small"
          startIcon={<DownloadIcon />}
          onClick={handleExport}
          disabled={trades.length === 0}
        >
          Export CSV
        </Button>
      </Box>

      <Card>
        <TradeFilterBar
          value={filters}
          onChange={handleFiltersChange}
          onReset={handleReset}
        />
      </Card>

      {errorMsg ? <Alert severity="error">{errorMsg}</Alert> : null}

      <Card sx={styles.card}>
        <Stack>
          <Box sx={styles.tableWrap}>
            <TradeTable trades={trades} loading={tradesQ.isLoading} />
          </Box>
          <CardContent sx={{ p: 0 }}>
            <TablePagination
              component="div"
              count={total}
              page={page}
              onPageChange={(_, p) => setPage(p)}
              rowsPerPage={rowsPerPage}
              onRowsPerPageChange={(e) => {
                setRowsPerPage(Number(e.target.value));
                setPage(0);
              }}
              rowsPerPageOptions={ROWS_PER_PAGE_OPTIONS}
            />
          </CardContent>
        </Stack>
      </Card>
    </Box>
  );
}
