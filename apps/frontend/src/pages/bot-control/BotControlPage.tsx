import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Stack,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Controller, useForm, type Resolver } from "react-hook-form";
import { useState } from "react";
import {
  StartRequestSchema,
  getBotStatus,
  pauseBot,
  startBot,
  stopBot,
  type BotState,
  type BotStatus,
  type StartRequest,
} from "../../api/bot";
import ModeSelector from "./ModeSelector";
import StrategyPicker from "./StrategyPicker";
import SymbolTimeframePicker from "./SymbolTimeframePicker";
import RiskFormFields from "./RiskFormFields";

const STATUS_REFETCH_MS = 2000;

const STATE_COLOR: Record<BotState, "default" | "success" | "warning" | "error"> = {
  idle: "default",
  running: "success",
  paused: "warning",
  halted: "error",
};

const styles = {
  root: { p: 3, display: "flex", flexDirection: "column", gap: 3 },
  formGrid: {
    display: "grid",
    gap: 2,
    gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
  },
  statusRow: { display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" },
  actions: { display: "flex", gap: 1, flexWrap: "wrap" },
} as const;

const DEFAULTS: StartRequest = {
  mode: "paper",
  strategy: "ma_cross",
  symbol: "BTCUSDT",
  timeframe: "1m",
  risk: {
    max_position_pct: 0.02,
    max_daily_drawdown_pct: 0.05,
    max_slippage_bps: 30,
    stop_loss_fraction: 0.05,
  },
};

const zodResolver: Resolver<StartRequest> = async (values) => {
  const parsed = StartRequestSchema.safeParse(values);
  if (parsed.success) {
    return { values: parsed.data, errors: {} };
  }
  const errors: Record<string, { type: string; message: string }> = {};
  for (const issue of parsed.error.issues) {
    const path = issue.path.join(".") || "_root";
    if (!errors[path]) {
      errors[path] = { type: issue.code, message: issue.message };
    }
  }
  // react-hook-form expects nested errors; flat keys are fine for our usage
  // because we read them via path traversal in RiskFormFields.
  const nested: Record<string, unknown> = {};
  for (const [path, err] of Object.entries(errors)) {
    const parts = path.split(".");
    let cur: Record<string, unknown> = nested;
    for (let i = 0; i < parts.length - 1; i += 1) {
      const next = (cur[parts[i]] ?? {}) as Record<string, unknown>;
      cur[parts[i]] = next;
      cur = next;
    }
    cur[parts[parts.length - 1]] = err;
  }
  return {
    values: {} as StartRequest,
    errors: nested as never,
  };
};

function StatusBlock({ status }: { status: BotStatus | undefined }) {
  if (!status) {
    return <Chip label="UNKNOWN" size="small" />;
  }
  return (
    <Box sx={styles.statusRow}>
      <Chip
        label={status.state.toUpperCase()}
        color={STATE_COLOR[status.state]}
        size="small"
        sx={{ fontWeight: 600 }}
      />
      <Typography sx={{ color: "text.secondary" }}>
        mode: <strong>{status.mode}</strong>
      </Typography>
      <Typography sx={{ color: "text.secondary" }}>
        symbol: <strong>{status.symbol || "—"}</strong>
      </Typography>
      {status.last_error ? (
        <Typography sx={{ color: "error.main" }}>
          last error: {status.last_error}
        </Typography>
      ) : null}
    </Box>
  );
}

export default function BotControlPage() {
  const qc = useQueryClient();
  const [submitMsg, setSubmitMsg] = useState<{
    kind: "ok" | "err";
    text: string;
  } | null>(null);

  const statusQ = useQuery({
    queryKey: ["bot", "status"],
    queryFn: getBotStatus,
    refetchInterval: STATUS_REFETCH_MS,
  });

  const {
    control,
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<StartRequest>({
    defaultValues: DEFAULTS,
    resolver: zodResolver,
    mode: "onSubmit",
  });

  const startM = useMutation({
    mutationFn: startBot,
    onSuccess: (data) => {
      qc.setQueryData(["bot", "status"], data);
      qc.invalidateQueries({ queryKey: ["bot", "status"] });
      setSubmitMsg({
        kind: "ok",
        text: `Bot started — runtime is ${data.state}.`,
      });
    },
    onError: (err: unknown) => {
      const m =
        err && typeof err === "object" && "message" in err
          ? String((err as { message: unknown }).message)
          : "Failed to start bot";
      setSubmitMsg({ kind: "err", text: m });
    },
  });

  const stopM = useMutation({
    mutationFn: stopBot,
    onSuccess: (data) => {
      qc.setQueryData(["bot", "status"], data);
    },
  });

  const pauseM = useMutation({
    mutationFn: pauseBot,
    onSuccess: (data) => {
      qc.setQueryData(["bot", "status"], data);
    },
  });

  const onSubmit = (req: StartRequest) => {
    setSubmitMsg(null);
    return startM.mutateAsync(req);
  };

  return (
    <Box sx={styles.root}>
      <Typography variant="h5">Bot Control</Typography>

      <Card>
        <CardContent>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
            Runtime Status
          </Typography>
          {statusQ.isLoading ? (
            <CircularProgress size={20} />
          ) : statusQ.isError ? (
            <Typography color="error">
              Could not fetch /api/bot/status — backend may not be running.
            </Typography>
          ) : (
            <StatusBlock status={statusQ.data} />
          )}
          <Box sx={{ ...styles.actions, mt: 2 }}>
            <Button
              variant="outlined"
              onClick={() => pauseM.mutate()}
              disabled={pauseM.isPending || statusQ.data?.state !== "running"}
            >
              Pause
            </Button>
            <Button
              variant="outlined"
              color="error"
              onClick={() => stopM.mutate()}
              disabled={
                stopM.isPending ||
                statusQ.data?.state === "idle" ||
                statusQ.data?.state === "halted"
              }
            >
              Stop
            </Button>
          </Box>
        </CardContent>
      </Card>

      <Card component="form" onSubmit={handleSubmit(onSubmit)} noValidate>
        <CardContent>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
            Start Configuration
          </Typography>

          <Stack spacing={2}>
            <Box sx={styles.formGrid}>
              <Controller
                name="mode"
                control={control}
                render={({ field, fieldState }) => (
                  <ModeSelector
                    value={field.value}
                    onChange={field.onChange}
                    error={fieldState.error?.message}
                  />
                )}
              />
              <Controller
                name="strategy"
                control={control}
                render={({ field, fieldState }) => (
                  <StrategyPicker
                    value={field.value}
                    onChange={field.onChange}
                    error={fieldState.error?.message}
                  />
                )}
              />
            </Box>

            <Controller
              name="symbol"
              control={control}
              render={({ field: symField, fieldState: symFs }) => (
                <Controller
                  name="timeframe"
                  control={control}
                  render={({ field: tfField, fieldState: tfFs }) => (
                    <SymbolTimeframePicker
                      symbol={symField.value}
                      timeframe={tfField.value}
                      onSymbolChange={symField.onChange}
                      onTimeframeChange={tfField.onChange}
                      symbolError={symFs.error?.message}
                      timeframeError={tfFs.error?.message}
                    />
                  )}
                />
              )}
            />

            <Divider sx={{ my: 1 }}>
              <Typography variant="caption" sx={{ color: "text.secondary" }}>
                RISK
              </Typography>
            </Divider>

            <RiskFormFields<StartRequest>
              register={register}
              errors={errors}
              names={{
                maxPositionPct: "risk.max_position_pct",
                maxDailyDrawdownPct: "risk.max_daily_drawdown_pct",
                maxSlippageBps: "risk.max_slippage_bps",
                stopLossFraction: "risk.stop_loss_fraction",
              }}
            />

            {submitMsg ? (
              <Alert severity={submitMsg.kind === "ok" ? "success" : "error"}>
                {submitMsg.text}
              </Alert>
            ) : null}

            <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
              <Button
                type="submit"
                variant="contained"
                disabled={
                  isSubmitting ||
                  startM.isPending ||
                  statusQ.data?.state === "running"
                }
              >
                {startM.isPending ? "Starting…" : "Start Bot"}
              </Button>
            </Box>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}

