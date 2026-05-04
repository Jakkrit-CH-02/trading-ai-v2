import { Box, Card, CardContent, Typography } from "@mui/material";
import type { EquityPoint } from "../../api/paper";
import { formatMoney } from "../../lib/format";

export interface EquityCurveProps {
  points: EquityPoint[];
  height?: number;
}

const styles = {
  empty: { color: "text.secondary", py: 6, textAlign: "center" },
  legend: {
    display: "flex",
    justifyContent: "space-between",
    mt: 1,
    color: "text.secondary",
    fontSize: 12,
  },
} as const;

export default function EquityCurve(props: EquityCurveProps) {
  const { points, height = 160 } = props;
  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
          P&L Curve (equity)
        </Typography>
        {points.length < 2 ? (
          <Typography sx={styles.empty}>
            Waiting for data — start the bot in paper mode to see the curve.
          </Typography>
        ) : (
          <Sparkline points={points} height={height} />
        )}
      </CardContent>
    </Card>
  );
}

function Sparkline({ points, height }: { points: EquityPoint[]; height: number }) {
  const values = points.map((p) => Number(p.equity)).filter(Number.isFinite);
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const width = 800;
  const stepX = width / (values.length - 1);
  const path = values
    .map((v, i) => {
      const x = i * stepX;
      const y = height - ((v - min) / range) * height;
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  const last = values[values.length - 1];
  const first = values[0];
  const up = last >= first;
  const stroke = up ? "#2e7d32" : "#c62828";
  const fill = up ? "rgba(46,125,50,0.12)" : "rgba(198,40,40,0.12)";
  const areaPath = `${path} L${width},${height} L0,${height} Z`;
  return (
    <Box sx={{ width: "100%" }}>
      <Box
        component="svg"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        sx={{ width: "100%", height, display: "block" }}
      >
        <path d={areaPath} fill={fill} stroke="none" />
        <path d={path} fill="none" stroke={stroke} strokeWidth={2} />
      </Box>
      <Box sx={styles.legend}>
        <span>min {formatMoney(min)}</span>
        <span>last {formatMoney(last)}</span>
        <span>max {formatMoney(max)}</span>
      </Box>
    </Box>
  );
}
