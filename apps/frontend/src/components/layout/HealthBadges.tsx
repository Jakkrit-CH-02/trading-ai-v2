import { Box, Tooltip, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import {
  getAIHealth,
  getBackendHealth,
  type AIHealth,
  type BackendHealth,
} from "../../api/health";

interface BadgeProps {
  label: string;
  ok: boolean;
  detail: string;
}

function Badge(props: BadgeProps) {
  return (
    <Tooltip title={props.detail} arrow>
      <Box
        sx={{
          display: "inline-flex",
          alignItems: "center",
          gap: 0.75,
          px: 1,
          py: 0.25,
          borderRadius: 1,
          bgcolor: "background.default",
          border: 1,
          borderColor: "divider",
        }}
      >
        <Box
          sx={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            bgcolor: props.ok ? "success.main" : "error.main",
          }}
        />
        <Typography variant="caption" sx={{ color: "text.secondary" }}>
          {props.label}
        </Typography>
      </Box>
    </Tooltip>
  );
}

function backendOk(d: BackendHealth | undefined): boolean {
  return !!d && d.status === "ok" && d.deps.postgres === "up" && d.deps.redis === "up";
}

function backendDetail(d: BackendHealth | undefined, err: unknown): string {
  if (err) return "backend unreachable";
  if (!d) return "checking…";
  return `status=${d.status} pg=${d.deps.postgres} redis=${d.deps.redis}`;
}

function aiOk(d: AIHealth | undefined): boolean {
  return !!d && d.status === "ok";
}

function aiDetail(d: AIHealth | undefined, err: unknown): string {
  if (err) return "ai unreachable";
  if (!d) return "checking…";
  return `status=${d.status} model_loaded=${d.model_loaded}`;
}

export default function HealthBadges() {
  const backend = useQuery({
    queryKey: ["health", "backend"],
    queryFn: getBackendHealth,
    refetchInterval: 5_000,
    retry: 0,
  });
  const ai = useQuery({
    queryKey: ["health", "ai"],
    queryFn: getAIHealth,
    refetchInterval: 5_000,
    retry: 0,
  });

  return (
    <Box sx={{ display: "inline-flex", gap: 1 }}>
      <Badge
        label="backend"
        ok={!backend.isError && backendOk(backend.data)}
        detail={backendDetail(backend.data, backend.error)}
      />
      <Badge
        label="ai"
        ok={!ai.isError && aiOk(ai.data)}
        detail={aiDetail(ai.data, ai.error)}
      />
    </Box>
  );
}
