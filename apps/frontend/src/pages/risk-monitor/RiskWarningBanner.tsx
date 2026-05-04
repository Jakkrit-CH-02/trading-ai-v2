import { Alert } from "@mui/material";
import type { RiskSnapshot } from "../../api/risk";

export interface RiskWarningBannerProps {
  snap: RiskSnapshot;
}

function pct(s: string): number {
  const n = Number(s);
  return Number.isFinite(n) ? n : 0;
}

export default function RiskWarningBanner(props: RiskWarningBannerProps) {
  const { snap } = props;
  const ddRatio =
    pct(snap.max_daily_drawdown_pct) > 0
      ? pct(snap.daily_drawdown_pct) / pct(snap.max_daily_drawdown_pct)
      : 0;
  const posRatio =
    pct(snap.max_position_pct) > 0
      ? pct(snap.largest_position_pct) / pct(snap.max_position_pct)
      : 0;

  if (snap.state === "halted") {
    return (
      <Alert severity="error">
        Bot halted — kill switch engaged or risk limits breached.
      </Alert>
    );
  }
  if (ddRatio >= 1) {
    return <Alert severity="error">Daily drawdown limit exceeded.</Alert>;
  }
  if (posRatio >= 1) {
    return <Alert severity="error">Position size limit exceeded.</Alert>;
  }
  if (ddRatio >= 0.75 || posRatio >= 0.75) {
    return (
      <Alert severity="warning">
        Approaching a risk limit — review exposure before continuing.
      </Alert>
    );
  }
  return null;
}
