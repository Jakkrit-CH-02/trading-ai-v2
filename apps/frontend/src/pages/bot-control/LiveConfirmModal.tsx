import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField, Typography } from "@mui/material";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { LIVE_CONFIRM_PHRASE, confirmLiveTrading } from "../../api/bot";

interface LiveConfirmModalProps {
  open: boolean;
  onClose: () => void;
  onConfirmed: (token: string) => void;
  symbol: string;
  maxPositionPct: number;
  maxDailyDrawdownPct: number;
}

const styles = {
  warn: { fontWeight: 600, color: "error.main" },
  phraseLabel: { fontFamily: "monospace", fontWeight: 700 },
} as const;

export default function LiveConfirmModal(props: LiveConfirmModalProps) {
  const [typed, setTyped] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () => confirmLiveTrading(typed),
    onSuccess: (token) => {
      setTyped("");
      setErr(null);
      props.onConfirmed(token);
    },
    onError: (e: unknown) => {
      const msg = e && typeof e === "object" && "message" in e
        ? String((e as { message: unknown }).message)
        : "Confirmation failed";
      setErr(msg);
    },
  });

  const phraseMatches = typed === LIVE_CONFIRM_PHRASE;

  return (
    <Dialog open={props.open} onClose={props.onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={styles.warn}>Enable LIVE Trading</DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          <Alert severity="error">
            You are about to switch the bot to LIVE mode on Binance mainnet.
            Real funds will be placed at risk on every signal.
          </Alert>
          <Box>
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              Symbol
            </Typography>
            <Typography>{props.symbol}</Typography>
          </Box>
          <Box>
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              Max position size
            </Typography>
            <Typography>{(props.maxPositionPct * 100).toFixed(2)}% of equity</Typography>
          </Box>
          <Box>
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              Max daily drawdown
            </Typography>
            <Typography>{(props.maxDailyDrawdownPct * 100).toFixed(2)}%</Typography>
          </Box>
          <Typography variant="body2">
            To proceed, type{" "}
            <Box component="span" sx={styles.phraseLabel}>
              {LIVE_CONFIRM_PHRASE}
            </Box>{" "}
            below.
          </Typography>
          <TextField
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={LIVE_CONFIRM_PHRASE}
            fullWidth
            autoFocus
            inputProps={{ "aria-label": "live confirmation phrase" }}
          />
          {err ? <Alert severity="error">{err}</Alert> : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => { setTyped(""); setErr(null); props.onClose(); }}>Cancel</Button>
        <Button
          color="error"
          variant="contained"
          disabled={!phraseMatches || m.isPending}
          onClick={() => m.mutate()}
        >
          {m.isPending ? "Confirming…" : "I UNDERSTAND — proceed"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
