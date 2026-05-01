import { Box, Typography } from "@mui/material";
import { Route, Routes, Link } from "react-router-dom";

function DashboardPlaceholder() {
  return <Typography sx={{ p: 3 }}>Dashboard (placeholder)</Typography>;
}

function BotControlPlaceholder() {
  return <Typography sx={{ p: 3 }}>Bot Control (placeholder)</Typography>;
}

export default function App() {
  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      <Box
        component="nav"
        sx={{
          width: 220,
          p: 2,
          borderRight: 1,
          borderColor: "divider",
          display: "flex",
          flexDirection: "column",
          gap: 1,
        }}
      >
        <Typography variant="h6" sx={{ mb: 2 }}>
          Trading Bot
        </Typography>
        <Link to="/" style={{ color: "inherit" }}>
          Dashboard
        </Link>
        <Link to="/bot" style={{ color: "inherit" }}>
          Bot Control
        </Link>
      </Box>
      <Box component="main" sx={{ flex: 1 }}>
        <Routes>
          <Route path="/" element={<DashboardPlaceholder />} />
          <Route path="/bot" element={<BotControlPlaceholder />} />
        </Routes>
      </Box>
    </Box>
  );
}
