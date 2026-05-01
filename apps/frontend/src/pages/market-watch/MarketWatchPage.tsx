import { useMemo, useState } from "react";
import {
  Box,
  Card,
  CircularProgress,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TableSortLabel,
  TextField,
  Typography,
} from "@mui/material";
import { useQueries, useQuery } from "@tanstack/react-query";
import { getCandles, getSnapshot, getSymbols } from "../../api/market";
import Sparkline from "./Sparkline";

type SortKey = "symbol" | "price" | "change";
type SortDir = "asc" | "desc";

interface Row {
  symbol: string;
  price: number | null;
  priceStr: string;
  change: number | null;
  spark: number[];
  loading: boolean;
}

const REFETCH_MS = 2000;

const styles = {
  root: { p: 3, display: "flex", flexDirection: "column", gap: 2 },
  filters: { display: "flex", gap: 2, alignItems: "center", flexWrap: "wrap" },
  card: { p: 0, overflow: "hidden" },
  centerCell: { display: "flex", justifyContent: "center", alignItems: "center", py: 6 },
  changeCell: (n: number | null) => ({
    color:
      n == null
        ? "text.secondary"
        : n > 0
          ? "success.main"
          : n < 0
            ? "error.main"
            : "text.secondary",
    fontVariantNumeric: "tabular-nums",
  }),
  numCell: { fontVariantNumeric: "tabular-nums" },
} as const;

function fmtPrice(v: string | null): string {
  if (v == null) return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return v;
  if (n >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (n >= 1) return n.toFixed(4);
  return n.toFixed(6);
}

function fmtPct(n: number | null): string {
  if (n == null) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

export default function MarketWatchPage() {
  const [interval, setInterval] = useState<string>("1m");
  const [filter, setFilter] = useState<string>("");
  const [sortKey, setSortKey] = useState<SortKey>("symbol");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const symbolsQ = useQuery({
    queryKey: ["market", "symbols"],
    queryFn: getSymbols,
    refetchInterval: REFETCH_MS,
  });

  const symbols = symbolsQ.data?.symbols ?? [];

  const snapshotQs = useQueries({
    queries: symbols.map((sym) => ({
      queryKey: ["market", "snapshot", sym, interval],
      queryFn: () => getSnapshot(sym, interval),
      refetchInterval: REFETCH_MS,
      enabled: symbols.length > 0,
    })),
  });

  const candleQs = useQueries({
    queries: symbols.map((sym) => ({
      queryKey: ["market", "candles", sym, interval, 30],
      queryFn: () => getCandles(sym, interval, 30),
      refetchInterval: REFETCH_MS,
      enabled: symbols.length > 0,
    })),
  });

  const rows: Row[] = useMemo(() => {
    return symbols.map((sym, i) => {
      const snap = snapshotQs[i]?.data;
      const candles = candleQs[i]?.data;
      const spark = candles?.bars.map((b) => Number(b.close)) ?? [];
      const price = snap ? Number(snap.latest.close) : null;
      let change: number | null = null;
      if (spark.length >= 2) {
        const first = spark[0];
        const last = spark[spark.length - 1];
        if (first > 0) change = ((last - first) / first) * 100;
      }
      return {
        symbol: sym,
        price,
        priceStr: snap?.latest.close ?? "",
        change,
        spark,
        loading:
          (snapshotQs[i]?.isLoading ?? false) ||
          (candleQs[i]?.isLoading ?? false),
      };
    });
  }, [symbols, snapshotQs, candleQs]);

  const filtered = useMemo(() => {
    const f = filter.trim().toUpperCase();
    const list = f ? rows.filter((r) => r.symbol.includes(f)) : rows;
    const dir = sortDir === "asc" ? 1 : -1;
    return [...list].sort((a, b) => {
      if (sortKey === "symbol") return a.symbol.localeCompare(b.symbol) * dir;
      const av = sortKey === "price" ? a.price : a.change;
      const bv = sortKey === "price" ? b.price : b.change;
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return (av - bv) * dir;
    });
  }, [rows, filter, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "symbol" ? "asc" : "desc");
    }
  }

  return (
    <Box sx={styles.root}>
      <Typography variant="h5">Market Watch</Typography>

      <Stack sx={styles.filters} direction="row">
        <TextField
          size="small"
          label="Filter"
          placeholder="BTC"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          sx={{ width: 220 }}
        />
        <Select
          size="small"
          value={interval}
          onChange={(e) => setInterval(e.target.value)}
          sx={{ width: 120 }}
        >
          {["1m", "5m", "15m", "1h", "4h", "1d"].map((tf) => (
            <MenuItem key={tf} value={tf}>
              {tf}
            </MenuItem>
          ))}
        </Select>
        {symbolsQ.isFetching ? (
          <CircularProgress size={16} sx={{ ml: 1 }} />
        ) : null}
      </Stack>

      <Card sx={styles.card}>
        {symbolsQ.isLoading ? (
          <Box sx={styles.centerCell}>
            <CircularProgress />
          </Box>
        ) : symbolsQ.isError ? (
          <Box sx={styles.centerCell}>
            <Typography color="error">Failed to load symbols.</Typography>
          </Box>
        ) : symbols.length === 0 ? (
          <Box sx={styles.centerCell}>
            <Typography sx={{ color: "text.secondary" }}>
              No symbols configured.
            </Typography>
          </Box>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>
                  <TableSortLabel
                    active={sortKey === "symbol"}
                    direction={sortDir}
                    onClick={() => toggleSort("symbol")}
                  >
                    Symbol
                  </TableSortLabel>
                </TableCell>
                <TableCell align="right">
                  <TableSortLabel
                    active={sortKey === "price"}
                    direction={sortDir}
                    onClick={() => toggleSort("price")}
                  >
                    Price
                  </TableSortLabel>
                </TableCell>
                <TableCell align="right">
                  <TableSortLabel
                    active={sortKey === "change"}
                    direction={sortDir}
                    onClick={() => toggleSort("change")}
                  >
                    Change
                  </TableSortLabel>
                </TableCell>
                <TableCell align="right">Sparkline</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filtered.map((r) => (
                <TableRow key={r.symbol} hover>
                  <TableCell sx={{ fontWeight: 600 }}>{r.symbol}</TableCell>
                  <TableCell align="right" sx={styles.numCell}>
                    {fmtPrice(r.priceStr || null)}
                  </TableCell>
                  <TableCell align="right" sx={styles.changeCell(r.change)}>
                    {fmtPct(r.change)}
                  </TableCell>
                  <TableCell align="right">
                    <Sparkline values={r.spark} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
    </Box>
  );
}
