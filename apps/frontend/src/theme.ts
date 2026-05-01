import { createTheme } from "@mui/material/styles";

export const theme = createTheme({
  palette: {
    mode: "dark",
    primary: { main: "#4ade80" },
    background: { default: "#0b0f14", paper: "#121821" },
  },
  typography: {
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    fontSize: 14,
  },
  shape: { borderRadius: 8 },
});
