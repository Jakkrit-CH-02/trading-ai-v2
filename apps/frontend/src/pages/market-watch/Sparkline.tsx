import { Box } from "@mui/material";

export interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
}

export default function Sparkline(props: SparklineProps) {
  const { values, width = 120, height = 32 } = props;
  if (values.length < 2) {
    return <Box sx={{ width, height }} />;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const stepX = width / (values.length - 1);
  const points = values
    .map((v, i) => {
      const x = i * stepX;
      const y = height - ((v - min) / range) * height;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  const up = values[values.length - 1] >= values[0];
  const stroke = up ? "#26a69a" : "#ef5350";
  return (
    <Box sx={{ width, height, display: "inline-block" }}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <polyline
          fill="none"
          stroke={stroke}
          strokeWidth={1.5}
          points={points}
        />
      </svg>
    </Box>
  );
}
