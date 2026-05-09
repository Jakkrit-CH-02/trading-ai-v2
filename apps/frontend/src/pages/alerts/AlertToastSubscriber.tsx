import {
  Alert as MuiAlert,
  Box,
  IconButton,
  Typography,
  alpha,
  type SxProps,
  type Theme,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { listAlerts, type Alert } from "../../api/alerts";

const AUTO_DISMISS_MS = 8000;
const MAX_VISIBLE = 4;

const SEVERITY_TO_MUI: Record<Alert["severity"], "info" | "warning" | "error"> = {
  info: "info",
  warning: "warning",
  critical: "error",
};

const containerSx: SxProps<Theme> = {
  position: "fixed",
  top: "72px",
  right: "16px",
  zIndex: 2000,
  display: "flex",
  flexDirection: "column",
  gap: "8px",
  width: "360px",
  maxWidth: "calc(100vw - 32px)",
};

const toastSx: SxProps<Theme> = {
  boxShadow: (theme) =>
    `0 8px 16px -4px ${alpha(theme.palette.grey[500], 0.16)}`,
  "& .MuiAlert-icon": { alignItems: "center", py: 0, mr: 1.5 },
  "& .MuiAlert-message": { py: 0, overflow: "hidden" },
  "& .MuiAlert-action": { alignItems: "flex-start", pt: 0.25, pr: 0 },
};

interface ToastItem {
  id: string;
  severity: Alert["severity"];
  message: string;
  timestamp: number;
}

export default function AlertToastSubscriber() {
  const { data, dataUpdatedAt } = useQuery({
    queryKey: ["alerts"],
    queryFn: listAlerts,
    refetchInterval: 5000,
  });

  const seenIds = useRef(new Set<string>());
  const lastProcessed = useRef(0);
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismiss = useCallback(
    (id: string) => setToasts((prev) => prev.filter((t) => t.id !== id)),
    [],
  );

  // Reset refs on unmount only (handles StrictMode double-mount)
  useEffect(() => {
    return () => {
      seenIds.current = new Set();
      lastProcessed.current = 0;
    };
  }, []);

  // Process new alerts when data changes
  useEffect(() => {
    if (!data || dataUpdatedAt === lastProcessed.current) return;
    lastProcessed.current = dataUpdatedAt;

    const now = Date.now();
    const isFirst = seenIds.current.size === 0;
    const fresh: ToastItem[] = [];

    for (const a of data) {
      if (seenIds.current.has(a.id)) continue;
      seenIds.current.add(a.id);
      if (!a.read) {
        fresh.push({ id: a.id, severity: a.severity, message: a.message, timestamp: now });
      }
    }

    if (fresh.length > 0) {
      const toShow = isFirst ? fresh.slice(0, MAX_VISIBLE) : fresh;
      setToasts((prev) => {
        const existing = new Set(prev.map((t) => t.id));
        const unique = toShow.filter((t) => !existing.has(t.id));
        return [...prev, ...unique].slice(-MAX_VISIBLE);
      });
    }
  }, [data, dataUpdatedAt]);

  // Auto-dismiss oldest toast
  useEffect(() => {
    if (toasts.length === 0) return;
    const oldest = toasts[0];
    const elapsed = Date.now() - oldest.timestamp;
    const remaining = Math.max(AUTO_DISMISS_MS - elapsed, 0);
    const timer = setTimeout(() => dismiss(oldest.id), remaining);
    return () => clearTimeout(timer);
  }, [toasts, dismiss]);

  if (toasts.length === 0) return null;

  return createPortal(
    <Box sx={containerSx}>
      {toasts.map((t) => (
        <MuiAlert
          key={t.id}
          severity={SEVERITY_TO_MUI[t.severity]}
          variant="standard"
          sx={toastSx}
          action={
            <IconButton size="small" onClick={() => dismiss(t.id)}>
              <CloseIcon sx={{ fontSize: 16 }} />
            </IconButton>
          }
        >
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {t.message}
          </Typography>
        </MuiAlert>
      ))}
    </Box>,
    document.body,
  );
}
