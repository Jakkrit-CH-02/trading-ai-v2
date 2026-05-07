import { Alert as MuiAlert, Snackbar, Stack } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { listAlerts, type Alert } from "../../api/alerts";

const styles = {
  stack: { width: { xs: "100%", sm: 380 } },
} as const;

const SEVERITY_TO_MUI: Record<
  Alert["severity"],
  "info" | "warning" | "error"
> = {
  info: "info",
  warning: "warning",
  critical: "error",
};

interface ToastItem {
  id: string;
  severity: Alert["severity"];
  message: string;
}

export default function AlertToastSubscriber() {
  const { data } = useQuery({
    queryKey: ["alerts"],
    queryFn: listAlerts,
    refetchInterval: 5000,
  });

  const seenIds = useRef<Set<string>>(new Set());
  const initialized = useRef(false);
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  useEffect(() => {
    if (!data) return;
    if (!initialized.current) {
      data.forEach((a) => seenIds.current.add(a.id));
      initialized.current = true;
      return;
    }
    const fresh: ToastItem[] = [];
    for (const a of data) {
      if (a.read) continue;
      if (seenIds.current.has(a.id)) continue;
      seenIds.current.add(a.id);
      fresh.push({ id: a.id, severity: a.severity, message: a.message });
    }
    if (fresh.length > 0) {
      setToasts((prev) => [...prev, ...fresh]);
    }
  }, [data]);

  const dismiss = (id: string) =>
    setToasts((prev) => prev.filter((t) => t.id !== id));

  return (
    <Snackbar
      open={toasts.length > 0}
      anchorOrigin={{ vertical: "top", horizontal: "right" }}
    >
      <Stack spacing={1} sx={styles.stack}>
        {toasts.slice(-4).map((t) => (
          <MuiAlert
            key={t.id}
            severity={SEVERITY_TO_MUI[t.severity]}
            variant="filled"
            onClose={() => dismiss(t.id)}
          >
            {t.message}
          </MuiAlert>
        ))}
      </Stack>
    </Snackbar>
  );
}
