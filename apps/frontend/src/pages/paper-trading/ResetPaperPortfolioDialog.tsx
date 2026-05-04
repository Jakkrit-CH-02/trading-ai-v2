import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
} from "@mui/material";

export interface ResetPaperPortfolioDialogProps {
  open: boolean;
  pending: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export default function ResetPaperPortfolioDialog(
  props: ResetPaperPortfolioDialogProps,
) {
  const { open, pending, onCancel, onConfirm } = props;
  return (
    <Dialog open={open} onClose={pending ? undefined : onCancel}>
      <DialogTitle>Reset paper portfolio?</DialogTitle>
      <DialogContent>
        <DialogContentText>
          This will close all simulated positions, clear the trade history, and
          restore the initial cash balance. The action cannot be undone.
        </DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} disabled={pending}>
          Cancel
        </Button>
        <Button
          onClick={onConfirm}
          color="error"
          variant="contained"
          disabled={pending}
        >
          {pending ? "Resetting…" : "Reset"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
