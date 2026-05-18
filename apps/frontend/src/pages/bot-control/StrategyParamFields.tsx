import { TextField } from "@mui/material";
import { Box } from "@mui/material";
import { Controller } from "react-hook-form";
import type { Control } from "react-hook-form";
import type { StartRequest } from "../../api/bot";
import type { StrategyId } from "./StrategyPicker";

interface StrategyParamFieldsProps {
  strategy: StrategyId;
  control: Control<StartRequest>;
}

export default function StrategyParamFields({ strategy, control }: StrategyParamFieldsProps) {
  if (strategy === "ma_cross") {
    return (
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" } }}>
        <Controller
          name={"strategy_params.fast" as "strategy_params"}
          control={control}
          render={({ field }) => (
            <TextField
              {...field}
              size="small"
              type="number"
              label="Fast Period"
              helperText="Short EMA period (default 9)"
              inputProps={{ step: "1", min: 1 }}
            />
          )}
        />
        <Controller
          name={"strategy_params.slow" as "strategy_params"}
          control={control}
          render={({ field }) => (
            <TextField
              {...field}
              size="small"
              type="number"
              label="Slow Period"
              helperText="Long EMA period (default 21)"
              inputProps={{ step: "1", min: 1 }}
            />
          )}
        />
      </Box>
    );
  }
  if (strategy === "rsi") {
    return (
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "repeat(3, 1fr)" } }}>
        <Controller
          name={"strategy_params.period" as "strategy_params"}
          control={control}
          render={({ field }) => (
            <TextField
              {...field}
              size="small"
              type="number"
              label="Period"
              helperText="RSI lookback (default 14)"
              inputProps={{ step: "1", min: 2 }}
            />
          )}
        />
        <Controller
          name={"strategy_params.oversold" as "strategy_params"}
          control={control}
          render={({ field }) => (
            <TextField
              {...field}
              size="small"
              type="number"
              label="Oversold"
              helperText="BUY below this (default 30)"
              inputProps={{ step: "1", min: 1, max: 99 }}
            />
          )}
        />
        <Controller
          name={"strategy_params.overbought" as "strategy_params"}
          control={control}
          render={({ field }) => (
            <TextField
              {...field}
              size="small"
              type="number"
              label="Overbought"
              helperText="SELL above this (default 70)"
              inputProps={{ step: "1", min: 1, max: 100 }}
            />
          )}
        />
      </Box>
    );
  }
  return null;
}
