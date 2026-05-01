import { createTheme } from "@mui/material/styles";

const monoStack =
  '"JetBrains Mono", "Fira Code", "SF Mono", Menlo, Monaco, Consolas, "Courier New", monospace';

declare module "@mui/material/styles" {
  interface TypographyVariants {
    money: React.CSSProperties;
  }
  interface TypographyVariantsOptions {
    money?: React.CSSProperties;
  }
}

declare module "@mui/material/Typography" {
  interface TypographyPropsVariantOverrides {
    money: true;
  }
}

export const theme = createTheme({
  palette: {
    mode: "dark",
    primary: { main: "#4ade80" },
    secondary: { main: "#60a5fa" },
    error: { main: "#f87171" },
    success: { main: "#4ade80" },
    warning: { main: "#fbbf24" },
    background: { default: "#0b0f14", paper: "#121821" },
    divider: "rgba(148, 163, 184, 0.16)",
    text: {
      primary: "#e2e8f0",
      secondary: "#94a3b8",
    },
  },
  typography: {
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    fontSize: 14,
    money: {
      fontFamily: monoStack,
      fontVariantNumeric: "tabular-nums",
      letterSpacing: 0,
    },
  },
  shape: { borderRadius: 8 },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        ":root": {
          "--font-mono": monoStack,
        },
        body: {
          backgroundColor: "#0b0f14",
        },
      },
    },
    MuiTypography: {
      defaultProps: {
        variantMapping: {
          money: "span",
        },
      },
    },
  },
});

export const monoFontFamily = monoStack;
