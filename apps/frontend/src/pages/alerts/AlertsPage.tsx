import {
  Alert as MuiAlert,
  Badge,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ackAlert, listAlerts, type Alert } from "../../api/alerts";

const styles = {
  root: { p: 3, display: "flex", flexDirection: "column", gap: 2 },
  header: {
    display: "flex",
    alignItems: "baseline",
    justifyContent: "space-between",
    gap: 2,
    flexWrap: "wrap",
  },
  title: { fontWeight: 600 },
  filters: { display: "flex", gap: 2, flexWrap: "wrap", alignItems: "center" },
  filterField: { minWidth: 160 },
  message: { whiteSpace: "pre-wrap" },
  unread: { fontWeight: 600 },
  read: { color: "text.secondary" },
} as const;

const SEVERITY_COLOR: Record<
  Alert["severity"],
  "info" | "warning" | "error"
> = {
  info: "info",
  warning: "warning",
  critical: "error",
};

function fmtTs(ms: number): string {
  if (!ms) return "—";
  return new Date(ms).toLocaleString();
}

function toDay(ms: number): string {
  if (!ms) return "";
  const d = new Date(ms);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export default function AlertsPage() {
  const qc = useQueryClient();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["alerts"],
    queryFn: listAlerts,
    refetchInterval: 5000,
  });

  const [severity, setSeverity] = useState<"all" | Alert["severity"]>("all");
  const [type, setType] = useState<string>("all");
  const [day, setDay] = useState<string>("");
  const [showRead, setShowRead] = useState<boolean>(true);

  const ack = useMutation({
    mutationFn: (id: string) => ackAlert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });

  const types = useMemo(() => {
    const set = new Set<string>();
    (data ?? []).forEach((a) => set.add(a.type));
    return Array.from(set).sort();
  }, [data]);

  const filtered = useMemo<Alert[]>(() => {
    const items = data ?? [];
    return items.filter((a) => {
      if (severity !== "all" && a.severity !== severity) return false;
      if (type !== "all" && a.type !== type) return false;
      if (day && toDay(a.created_at) !== day) return false;
      if (!showRead && a.read) return false;
      return true;
    });
  }, [data, severity, type, day, showRead]);

  const unreadCount = useMemo(
    () => (data ?? []).filter((a) => !a.read).length,
    [data],
  );
  const criticalUnread = useMemo(
    () => (data ?? []).filter((a) => !a.read && a.severity === "critical"),
    [data],
  );

  if (isLoading) {
    return (
      <Box sx={{ p: 3, display: "flex", gap: 1, alignItems: "center" }}>
        <CircularProgress size={20} />
        <Typography>Loading alerts…</Typography>
      </Box>
    );
  }

  if (isError) {
    return (
      <Box sx={{ p: 3 }}>
        <MuiAlert severity="error">
          Failed to load alerts: {(error as Error)?.message ?? "unknown"}
        </MuiAlert>
      </Box>
    );
  }

  return (
    <Box sx={styles.root}>
      <Box sx={styles.header}>
        <Box>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Typography variant="h5" sx={styles.title}>
              Alerts
            </Typography>
            <Badge
              color="error"
              badgeContent={unreadCount}
              showZero={false}
              max={999}
            />
          </Stack>
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            Notifications, errors, warnings, and trade events.
          </Typography>
        </Box>
      </Box>

      {criticalUnread.length > 0 && (
        <MuiAlert severity="error" variant="filled">
          {criticalUnread.length} unacknowledged critical alert
          {criticalUnread.length > 1 ? "s" : ""}: {criticalUnread[0].message}
        </MuiAlert>
      )}

      <Card>
        <CardContent>
          <Box sx={styles.filters}>
            <TextField
              select
              label="Severity"
              size="small"
              value={severity}
              onChange={(e) =>
                setSeverity(e.target.value as typeof severity)
              }
              sx={styles.filterField}
              inputProps={{ "aria-label": "filter severity" }}
            >
              <MenuItem value="all">All</MenuItem>
              <MenuItem value="info">Info</MenuItem>
              <MenuItem value="warning">Warning</MenuItem>
              <MenuItem value="critical">Critical</MenuItem>
            </TextField>
            <TextField
              select
              label="Type"
              size="small"
              value={type}
              onChange={(e) => setType(e.target.value)}
              sx={styles.filterField}
              inputProps={{ "aria-label": "filter type" }}
            >
              <MenuItem value="all">All</MenuItem>
              {types.map((t) => (
                <MenuItem key={t} value={t}>
                  {t}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              type="date"
              label="Date"
              size="small"
              value={day}
              onChange={(e) => setDay(e.target.value)}
              InputLabelProps={{ shrink: true }}
              sx={styles.filterField}
              inputProps={{ "aria-label": "filter date" }}
            />
            <Button
              size="small"
              variant={showRead ? "outlined" : "contained"}
              onClick={() => setShowRead((v) => !v)}
            >
              {showRead ? "Hide read" : "Show read"}
            </Button>
            <Button
              size="small"
              onClick={() => {
                setSeverity("all");
                setType("all");
                setDay("");
                setShowRead(true);
              }}
            >
              Clear
            </Button>
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          {filtered.length === 0 ? (
            <Typography sx={{ color: "text.secondary", py: 2 }}>
              No alerts match the current filters.
            </Typography>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Time</TableCell>
                  <TableCell>Severity</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Message</TableCell>
                  <TableCell>Entity</TableCell>
                  <TableCell align="right">Action</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filtered.map((a) => (
                  <TableRow key={a.id} hover>
                    <TableCell sx={a.read ? styles.read : styles.unread}>
                      {fmtTs(a.created_at)}
                    </TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        color={SEVERITY_COLOR[a.severity]}
                        label={a.severity}
                      />
                    </TableCell>
                    <TableCell sx={a.read ? styles.read : styles.unread}>
                      {a.type}
                    </TableCell>
                    <TableCell sx={{ ...styles.message, ...(a.read ? styles.read : styles.unread) }}>
                      {a.message}
                    </TableCell>
                    <TableCell sx={{ color: "text.secondary" }}>
                      {a.entity || "—"}
                    </TableCell>
                    <TableCell align="right">
                      {a.read ? (
                        <Chip size="small" label="acked" variant="outlined" />
                      ) : (
                        <Button
                          size="small"
                          variant="outlined"
                          disabled={ack.isPending}
                          onClick={() => ack.mutate(a.id)}
                        >
                          Acknowledge
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
