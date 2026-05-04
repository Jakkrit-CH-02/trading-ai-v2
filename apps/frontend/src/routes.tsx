import {
  Dashboard as DashboardIcon,
  ShowChart as MarketIcon,
  SmartToy as BotIcon,
  Science as PaperIcon,
  Receipt as LogsIcon,
  Shield as RiskIcon,
  Replay as BacktestIcon,
  Psychology as AiIcon,
  NotificationsActive as AlertsIcon,
  Settings as SettingsIcon,
} from "@mui/icons-material";
import type { ComponentType } from "react";
import { Box, Typography } from "@mui/material";
import MarketWatchPage from "./pages/market-watch/MarketWatchPage";
import DashboardPage from "./pages/dashboard/DashboardPage";
import AITrainingPage from "./pages/ai-training/AITrainingPage";
import BotControlPage from "./pages/bot-control/BotControlPage";
import PaperTradingPage from "./pages/paper-trading/PaperTradingPage";
import TradeLogsPage from "./pages/trade-logs/TradeLogsPage";
import RiskMonitorPage from "./pages/risk-monitor/RiskMonitorPage";

export interface RouteDef {
  path: string;
  label: string;
  icon: ComponentType;
  element: ComponentType;
}

function makePlaceholder(title: string): ComponentType {
  function Placeholder() {
    return (
      <Box sx={{ p: 3 }}>
        <Typography variant="h5" sx={{ mb: 1 }}>
          {title}
        </Typography>
        <Typography sx={{ color: "text.secondary" }}>
          Placeholder — implementation pending.
        </Typography>
      </Box>
    );
  }
  return Placeholder;
}

export const routes: RouteDef[] = [
  {
    path: "/",
    label: "Dashboard",
    icon: DashboardIcon,
    element: DashboardPage,
  },
  {
    path: "/market",
    label: "Market Watch",
    icon: MarketIcon,
    element: MarketWatchPage,
  },
  {
    path: "/bot",
    label: "Bot Control",
    icon: BotIcon,
    element: BotControlPage,
  },
  {
    path: "/paper",
    label: "Paper Trading",
    icon: PaperIcon,
    element: PaperTradingPage,
  },
  {
    path: "/logs",
    label: "Trade Logs",
    icon: LogsIcon,
    element: TradeLogsPage,
  },
  {
    path: "/risk",
    label: "Risk Monitor",
    icon: RiskIcon,
    element: RiskMonitorPage,
  },
  {
    path: "/backtest",
    label: "Backtesting",
    icon: BacktestIcon,
    element: makePlaceholder("Backtesting"),
  },
  {
    path: "/ai",
    label: "AI Training",
    icon: AiIcon,
    element: AITrainingPage,
  },
  {
    path: "/alerts",
    label: "Alerts",
    icon: AlertsIcon,
    element: makePlaceholder("Alerts"),
  },
  {
    path: "/settings",
    label: "Settings",
    icon: SettingsIcon,
    element: makePlaceholder("Settings"),
  },
];
