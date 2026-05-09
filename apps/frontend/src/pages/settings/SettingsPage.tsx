import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  MenuItem,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  SettingsSchema,
  getSettings,
  updateSettings,
  type Settings,
} from "../../api/settings";
import RiskSettingsForm from "./RiskSettingsForm";
import NotificationSettingsForm from "./NotificationSettingsForm";
import ApiKeyStatusCard from "./ApiKeyStatusCard";

const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"] as const;

const styles = {
  root: { p: 3, display: "flex", flexDirection: "column", gap: 3 },
  header: {
    display: "flex",
    alignItems: "baseline",
    justifyContent: "space-between",
    gap: 2,
    flexWrap: "wrap",
  },
  cardTitle: { fontWeight: 600 },
  generalGrid: {
    display: "grid",
    gap: 2,
    gridTemplateColumns: { xs: "1fr", md: "1fr 1fr 1fr" },
  },
  modeRow: { display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" },
  actions: { display: "flex", gap: 1, justifyContent: "flex-end" },
  loading: { display: "flex", alignItems: "center", gap: 1, p: 3 },
} as const;

type Errors = Partial<Record<keyof Settings, string>>;

function validate(s: Settings): Errors {
  const errs: Errors = {};
  const pos = Number(s.max_position_pct);
  if (!Number.isFinite(pos) || pos <= 0 || pos > 1) {
    errs.max_position_pct = "Must be > 0 and ≤ 1";
  }
  const dd = Number(s.max_daily_drawdown_pct);
  if (!Number.isFinite(dd) || dd <= 0 || dd > 1) {
    errs.max_daily_drawdown_pct = "Must be > 0 and ≤ 1";
  }
  if (s.max_slippage_bps < 0 || s.max_slippage_bps > 10_000) {
    errs.max_slippage_bps = "0–10000";
  }
  if (!s.default_symbol.trim()) {
    errs.default_symbol = "Required";
  }
  if (
    s.notify_webhook_url &&
    !/^https?:\/\//i.test(s.notify_webhook_url)
  ) {
    errs.notify_webhook_url = "Must start with http(s)://";
  }
  return errs;
}

export default function SettingsPage() {
  const qc = useQueryClient();
  const { data, isLoading, isError, error } = useQuery<Settings>({
    queryKey: ["settings"],
    queryFn: getSettings,
  });

  const [draft, setDraft] = useState<Settings | null>(null);
  const [confirmLive, setConfirmLive] = useState(false);
  const [showSaved, setShowSaved] = useState(false);

  useEffect(() => {
    if (data && !draft) setDraft(data);
  }, [data, draft]);

  const errors = useMemo<Errors>(() => (draft ? validate(draft) : {}), [draft]);

  const dirty = useMemo(() => {
    if (!draft || !data) return false;
    return JSON.stringify(draft) !== JSON.stringify(data);
  }, [draft, data]);

  const save = useMutation({
    mutationFn: (input: Settings) => updateSettings(input),
    onSuccess: (out) => {
      const parsed = SettingsSchema.parse(out);
      qc.setQueryData(["settings"], parsed);
      setDraft(parsed);
      setShowSaved(true);
      setConfirmLive(false);
    },
  });

  if (isLoading || !draft) {
    return (
      <Box sx={styles.loading}>
        <CircularProgress size={20} />
        <Typography>Loading settings…</Typography>
      </Box>
    );
  }

  if (isError) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error">
          Failed to load settings: {(error as Error)?.message ?? "unknown"}
        </Alert>
      </Box>
    );
  }

  function patch(p: Partial<Settings>) {
    setDraft((prev) => (prev ? { ...prev, ...p } : prev));
    setShowSaved(false);
  }

  const liveSelected = draft.default_mode === "live";
  const canSave =
    Object.keys(errors).length === 0 &&
    dirty &&
    !save.isPending &&
    (!liveSelected || confirmLive);

  return (
    <Box sx={styles.root}>
      <Box sx={styles.header}>
        <Box>
          <Typography variant="h5" sx={styles.cardTitle}>
            Settings
          </Typography>
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            Risk thresholds, notifications, default mode, and API key status.
          </Typography>
        </Box>
        {save.isError && (
          <Alert severity="error">
            {(save.error as Error)?.message ?? "Save failed"}
          </Alert>
        )}
        {showSaved && !dirty && (
          <Alert severity="success">Saved.</Alert>
        )}
      </Box>

      <Card>
        <CardContent>
          <Typography variant="subtitle1" sx={styles.cardTitle} gutterBottom>
            General
          </Typography>
          <Box sx={styles.generalGrid}>
            <TextField
              label="Default symbol"
              value={draft.default_symbol}
              onChange={(e) =>
                patch({ default_symbol: e.target.value.toUpperCase() })
              }
              error={Boolean(errors.default_symbol)}
              helperText={errors.default_symbol ?? "e.g. BTCUSDT"}
              inputProps={{ "aria-label": "default symbol" }}
            />
            <TextField
              select
              label="Default timeframe"
              value={draft.default_timeframe}
              onChange={(e) =>
                patch({
                  default_timeframe:
                    e.target.value as Settings["default_timeframe"],
                })
              }
              inputProps={{ "aria-label": "default timeframe" }}
            >
              {TIMEFRAMES.map((tf) => (
                <MenuItem key={tf} value={tf}>
                  {tf}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Default mode"
              value={draft.default_mode}
              onChange={(e) => {
                patch({
                  default_mode: e.target.value as Settings["default_mode"],
                });
                setConfirmLive(false);
              }}
              inputProps={{ "aria-label": "default mode" }}
            >
              <MenuItem value="paper">Paper (testnet)</MenuItem>
              <MenuItem value="live">Live (mainnet)</MenuItem>
            </TextField>
          </Box>
          {liveSelected && (
            <Alert
              severity="warning"
              sx={{ mt: 2 }}
              action={
                <Button
                  color="warning"
                  size="small"
                  variant={confirmLive ? "contained" : "outlined"}
                  onClick={() => setConfirmLive((v) => !v)}
                >
                  {confirmLive ? "Confirmed" : "I understand"}
                </Button>
              }
            >
              Live mode trades with real money. Confirm to enable saving.
            </Alert>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Box sx={styles.modeRow}>
            <Typography variant="subtitle1" sx={styles.cardTitle}>
              Risk thresholds
            </Typography>
            <Chip label="Enforced backend-side" size="small" />
          </Box>
          <Box sx={{ mt: 1.5 }}>
            <RiskSettingsForm
              value={draft}
              errors={errors}
              onChange={patch}
            />
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="subtitle1" sx={styles.cardTitle} gutterBottom>
            Notifications
          </Typography>
          <NotificationSettingsForm
            value={draft}
            errors={errors}
            onChange={patch}
          />
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="subtitle1" sx={styles.cardTitle} gutterBottom>
            Binance API key
          </Typography>
          <ApiKeyStatusCard />
        </CardContent>
      </Card>

      <Box sx={styles.actions}>
        <Button
          variant="text"
          disabled={!dirty || save.isPending}
          onClick={() => {
            if (data) setDraft(data);
            setConfirmLive(false);
            setShowSaved(false);
          }}
        >
          Reset
        </Button>
        <Button
          variant="contained"
          disabled={!canSave}
          onClick={() => draft && save.mutate(draft)}
        >
          {save.isPending ? "Saving…" : "Save changes"}
        </Button>
      </Box>
    </Box>
  );
}
