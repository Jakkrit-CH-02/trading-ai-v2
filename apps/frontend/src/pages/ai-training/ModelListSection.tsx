import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listModels,
  promoteModel,
  reloadModel,
  type Environment,
  type ListModelsResponse,
  type ModelMetadata,
} from "../../api/ai";

const styles = {
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    mb: 2,
    gap: 2,
  },
  cellWrap: { fontFamily: "monospace", fontSize: 12 },
  metricsCell: { fontSize: 12, color: "text.secondary" },
  actions: { display: "flex", gap: 1 },
} as const;

function formatMetrics(m: Record<string, number>): string {
  const keys = Object.keys(m);
  if (keys.length === 0) return "—";
  return keys
    .slice(0, 3)
    .map((k) => `${k}=${Number(m[k]).toFixed(3)}`)
    .join(", ");
}

export default function ModelListSection() {
  const qc = useQueryClient();
  const query = useQuery<ListModelsResponse, Error>({
    queryKey: ["ai", "models"],
    queryFn: listModels,
    refetchInterval: 5000,
  });

  const promote = useMutation<
    unknown,
    Error,
    { modelId: string; environment: Environment }
  >({
    mutationFn: ({ modelId, environment }) => promoteModel(modelId, environment),
    onSuccess: async () => {
      await reloadModel().catch(() => undefined);
      await qc.invalidateQueries({ queryKey: ["ai", "models"] });
    },
  });

  const active = query.data?.active;
  const models = query.data?.models ?? [];

  return (
    <Card>
      <CardContent>
        <Box sx={styles.header}>
          <Typography variant="h6">Model Registry</Typography>
          <Stack direction="row" spacing={1}>
            <Chip
              size="small"
              label={`paper: ${active?.paper ?? "—"}`}
              color={active?.paper ? "primary" : "default"}
            />
            <Chip
              size="small"
              label={`live: ${active?.live ?? "—"}`}
              color={active?.live ? "success" : "default"}
            />
          </Stack>
        </Box>

        {query.isError ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            {query.error.message}
          </Alert>
        ) : null}

        {promote.isError ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            {promote.error.message}
          </Alert>
        ) : null}

        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Version</TableCell>
              <TableCell>Model ID</TableCell>
              <TableCell>Dataset</TableCell>
              <TableCell>Metrics</TableCell>
              <TableCell>Evaluated</TableCell>
              <TableCell align="right">Promote</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {models.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6}>
                  <Typography variant="body2" sx={{ color: "text.secondary" }}>
                    No models registered yet — train one above.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : null}
            {models.map((m: ModelMetadata) => {
              const liveBlocked = !m.evaluated;
              return (
                <TableRow key={m.id}>
                  <TableCell>v{m.version}</TableCell>
                  <TableCell sx={styles.cellWrap}>{m.id}</TableCell>
                  <TableCell sx={styles.cellWrap}>{m.dataset_id}</TableCell>
                  <TableCell sx={styles.metricsCell}>
                    {formatMetrics(m.metrics)}
                  </TableCell>
                  <TableCell>
                    {m.evaluated ? (
                      <Chip size="small" color="success" label="yes" />
                    ) : (
                      <Chip size="small" label="no" />
                    )}
                  </TableCell>
                  <TableCell align="right">
                    <Box sx={styles.actions}>
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={promote.isPending}
                        onClick={() =>
                          promote.mutate({ modelId: m.id, environment: "paper" })
                        }
                      >
                        Paper
                      </Button>
                      <Button
                        size="small"
                        variant="outlined"
                        color="success"
                        disabled={promote.isPending || liveBlocked}
                        title={
                          liveBlocked
                            ? "Model has not passed evaluation"
                            : undefined
                        }
                        onClick={() =>
                          promote.mutate({ modelId: m.id, environment: "live" })
                        }
                      >
                        Live
                      </Button>
                    </Box>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
