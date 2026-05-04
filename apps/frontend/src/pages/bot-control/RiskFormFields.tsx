import { Box, TextField } from "@mui/material";
import type {
  FieldErrors,
  UseFormRegister,
  FieldValues,
  Path,
} from "react-hook-form";

export interface RiskFormFieldsProps<T extends FieldValues> {
  register: UseFormRegister<T>;
  errors: FieldErrors<T>;
  names: {
    maxPositionPct: Path<T>;
    maxDailyDrawdownPct: Path<T>;
    maxSlippageBps: Path<T>;
    stopLossFraction: Path<T>;
  };
}

export default function RiskFormFields<T extends FieldValues>(
  props: RiskFormFieldsProps<T>,
) {
  const { register, errors, names } = props;
  const err = (p: Path<T>): string | undefined => {
    const parts = (p as string).split(".");
    let node: unknown = errors;
    for (const part of parts) {
      if (node && typeof node === "object" && part in node) {
        node = (node as Record<string, unknown>)[part];
      } else {
        return undefined;
      }
    }
    if (
      node &&
      typeof node === "object" &&
      "message" in node &&
      typeof (node as { message?: unknown }).message === "string"
    ) {
      return (node as { message: string }).message;
    }
    return undefined;
  };

  return (
    <Box
      sx={{
        display: "grid",
        gap: 2,
        gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)" },
      }}
    >
      <TextField
        size="small"
        type="number"
        label="Max Position %"
        helperText={
          err(names.maxPositionPct) ?? "Fraction of equity per trade (0–1)"
        }
        error={Boolean(err(names.maxPositionPct))}
        inputProps={{ step: "0.01", min: 0, max: 1 }}
        {...register(names.maxPositionPct, { valueAsNumber: true })}
      />
      <TextField
        size="small"
        type="number"
        label="Max Daily Drawdown %"
        helperText={
          err(names.maxDailyDrawdownPct) ?? "Halts bot when reached (0–1)"
        }
        error={Boolean(err(names.maxDailyDrawdownPct))}
        inputProps={{ step: "0.01", min: 0, max: 1 }}
        {...register(names.maxDailyDrawdownPct, { valueAsNumber: true })}
      />
      <TextField
        size="small"
        type="number"
        label="Max Slippage (bps)"
        helperText={
          err(names.maxSlippageBps) ?? "Reject market orders above this"
        }
        error={Boolean(err(names.maxSlippageBps))}
        inputProps={{ step: "1", min: 0 }}
        {...register(names.maxSlippageBps, { valueAsNumber: true })}
      />
      <TextField
        size="small"
        type="number"
        label="Stop Loss Fraction"
        helperText={
          err(names.stopLossFraction) ?? "Stop = entry × (1 − fraction)"
        }
        error={Boolean(err(names.stopLossFraction))}
        inputProps={{ step: "0.01", min: 0, max: 1 }}
        {...register(names.stopLossFraction, { valueAsNumber: true })}
      />
    </Box>
  );
}
