import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getApiKeyStatus,
  testApiKey,
  type ApiKeyStatus,
} from "../../api/settings";

const styles = {
  row: { display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" },
  perms: { display: "flex", gap: 1, flexWrap: "wrap" },
  hint: { color: "text.secondary" },
} as const;

function permChip(label: string, ok: boolean) {
  return (
    <Chip
      key={label}
      label={label}
      size="small"
      color={ok ? "success" : "default"}
      variant={ok ? "filled" : "outlined"}
    />
  );
}

export default function ApiKeyStatusCard() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery<ApiKeyStatus>({
    queryKey: ["settings", "binance-key"],
    queryFn: getApiKeyStatus,
    retry: 0,
  });
  const test = useMutation({
    mutationFn: testApiKey,
    onSuccess: (out) => qc.setQueryData(["settings", "binance-key"], out),
  });

  if (isLoading) {
    return (
      <Box sx={styles.row}>
        <CircularProgress size={18} />
        <Typography variant="body2" sx={styles.hint}>
          Checking key status…
        </Typography>
      </Box>
    );
  }

  if (error || !data) {
    return (
      <Alert severity="warning">
        Unable to read API key status. Configure keys via the backend
        environment; this UI only displays masked status.
      </Alert>
    );
  }

  return (
    <Stack spacing={1.5}>
      <Box sx={styles.row}>
        <Chip
          label={data.configured ? "Configured" : "Not configured"}
          color={data.configured ? "success" : "default"}
          size="small"
        />
        <Chip
          label={data.testnet ? "Testnet" : "Mainnet"}
          color={data.testnet ? "info" : "warning"}
          size="small"
        />
        {data.masked_key && (
          <Typography variant="body2" sx={styles.hint}>
            Key: <code>{data.masked_key}</code>
          </Typography>
        )}
      </Box>
      <Box sx={styles.perms}>
        {permChip("read", data.permissions.read)}
        {permChip("spot trade", data.permissions.spot_trade)}
        {permChip("withdraw", data.permissions.withdraw)}
      </Box>
      <Typography variant="caption" sx={styles.hint}>
        Secrets are never displayed. Withdraw permission should be disabled.
      </Typography>
      <Box>
        <Button
          variant="outlined"
          size="small"
          disabled={test.isPending}
          onClick={() => test.mutate()}
        >
          {test.isPending ? "Testing…" : "Test connection"}
        </Button>
        {test.isError && (
          <Alert severity="error" sx={{ mt: 1 }}>
            Key test failed.
          </Alert>
        )}
      </Box>
    </Stack>
  );
}
