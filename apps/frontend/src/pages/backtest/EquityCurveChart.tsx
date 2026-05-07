import { Box, Card, CardContent, Typography } from "@mui/material";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { EquityPoint } from "../../api/backtest";

export interface EquityCurveChartProps {
  points: EquityPoint[];
}

const styles = {
  empty: { color: "text.secondary", py: 6, textAlign: "center" },
} as const;

export default function EquityCurveChart(props: EquityCurveChartProps) {
  const { points } = props;
  const data = points.map((p) => ({
    t: p.timestamp_ms,
    equity: Number(p.equity),
  }));
  const last = data[data.length - 1]?.equity ?? 0;
  const first = data[0]?.equity ?? 0;
  const up = last >= first;
  const stroke = up ? "#2e7d32" : "#c62828";
  const fill = up ? "rgba(46,125,50,0.18)" : "rgba(198,40,40,0.18)";
  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
          Equity Curve
        </Typography>
        {data.length < 2 ? (
          <Typography sx={styles.empty}>No equity data yet.</Typography>
        ) : (
          <Box sx={{ width: "100%", height: 280 }}>
            <ResponsiveContainer>
              <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#444" />
                <XAxis
                  dataKey="t"
                  tickFormatter={(v) =>
                    new Date(v as number).toISOString().slice(5, 16).replace("T", " ")
                  }
                  minTickGap={40}
                  stroke="#888"
                  fontSize={11}
                />
                <YAxis
                  domain={["auto", "auto"]}
                  stroke="#888"
                  fontSize={11}
                  width={70}
                  tickFormatter={(v) => Number(v).toFixed(0)}
                />
                <Tooltip
                  labelFormatter={(v) => new Date(v as number).toISOString()}
                  formatter={(v) => Number(v).toFixed(2)}
                  contentStyle={{ backgroundColor: "#1e1e1e", border: "1px solid #444" }}
                />
                <Area
                  type="monotone"
                  dataKey="equity"
                  stroke={stroke}
                  fill={fill}
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </Box>
        )}
      </CardContent>
    </Card>
  );
}
