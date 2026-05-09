import { createTheme, alpha } from "@mui/material/styles";

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

const GREY = {
  50: "#f9fafb",
  100: "#f4f6f8",
  200: "#f0f1f3",
  300: "#e4e6eb",
  400: "#c4cdd5",
  500: "#919eab",
  600: "#637381",
  700: "#454f5b",
  800: "#1c252e",
  900: "#141a21",
};

const PRIMARY = "#00A76F";
const PRIMARY_LIGHT = "#5BE49B";
const PRIMARY_DARK = "#007867";
const SECONDARY = "#8E33FF";
const INFO = "#00B8D9";
const SUCCESS = "#22C55E";
const WARNING = "#FFAB00";
const ERROR = "#FF5630";

const BG_DEFAULT = "#f9fafb";
const BG_PAPER = "#ffffff";

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: PRIMARY, light: PRIMARY_LIGHT, dark: PRIMARY_DARK, contrastText: "#ffffff" },
    secondary: { main: SECONDARY },
    info: { main: INFO },
    error: { main: ERROR },
    success: { main: SUCCESS },
    warning: { main: WARNING },
    background: { default: BG_DEFAULT, paper: BG_PAPER },
    divider: alpha(GREY[500], 0.16),
    text: {
      primary: GREY[800],
      secondary: GREY[600],
      disabled: GREY[500],
    },
    action: {
      hover: alpha(GREY[500], 0.08),
      selected: alpha(PRIMARY, 0.08),
      disabled: alpha(GREY[500], 0.8),
      disabledBackground: alpha(GREY[500], 0.24),
      focus: alpha(GREY[500], 0.24),
    },
  },
  typography: {
    fontFamily:
      '"Inter", "Public Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    fontSize: 14,
    fontWeightBold: 700,
    h1: { fontWeight: 800, fontSize: "2.5rem", lineHeight: 1.2, color: GREY[800] },
    h2: { fontWeight: 800, fontSize: "2rem", lineHeight: 1.3, color: GREY[800] },
    h3: { fontWeight: 700, fontSize: "1.5rem", lineHeight: 1.4, color: GREY[800] },
    h4: { fontWeight: 700, fontSize: "1.25rem", lineHeight: 1.5, color: GREY[800] },
    h5: { fontWeight: 700, fontSize: "1.125rem", lineHeight: 1.5, color: GREY[800] },
    h6: { fontWeight: 600, fontSize: "1rem", lineHeight: 1.5, color: GREY[800] },
    subtitle1: { fontWeight: 600, fontSize: "1rem", lineHeight: 1.5 },
    subtitle2: { fontWeight: 600, fontSize: "0.875rem", lineHeight: 1.57 },
    body1: { fontSize: "1rem", lineHeight: 1.5 },
    body2: { fontSize: "0.875rem", lineHeight: 1.57 },
    caption: { fontSize: "0.75rem", lineHeight: 1.5 },
    overline: {
      fontSize: "0.75rem",
      lineHeight: 1.5,
      fontWeight: 700,
      textTransform: "uppercase",
      letterSpacing: "0.08em",
    },
    button: { fontWeight: 700, fontSize: "0.875rem", textTransform: "none" },
    money: {
      fontFamily: monoStack,
      fontVariantNumeric: "tabular-nums",
      letterSpacing: 0,
    },
  },
  shape: { borderRadius: 12 },
  shadows: [
    "none",
    `0 1px 2px ${alpha(GREY[500], 0.16)}`,
    `0 2px 4px -1px ${alpha(GREY[500], 0.12)}`,
    `0 4px 8px -2px ${alpha(GREY[500], 0.12)}`,
    `0 6px 12px -3px ${alpha(GREY[500], 0.12)}`,
    `0 8px 16px -4px ${alpha(GREY[500], 0.12)}`,
    `0 12px 24px -4px ${alpha(GREY[500], 0.2)}`,
    `0 16px 32px -4px ${alpha(GREY[500], 0.2)}`,
    `0 20px 40px -4px ${alpha(GREY[500], 0.2)}`,
    `0 1px 2px 0 ${alpha(GREY[500], 0.16)}`,
    `0 1px 2px 0 ${alpha(GREY[500], 0.16)}`,
    `0 1px 2px 0 ${alpha(GREY[500], 0.16)}`,
    `0 1px 2px 0 ${alpha(GREY[500], 0.16)}`,
    `0 1px 2px 0 ${alpha(GREY[500], 0.16)}`,
    `0 1px 2px 0 ${alpha(GREY[500], 0.16)}`,
    `0 1px 2px 0 ${alpha(GREY[500], 0.16)}`,
    `0 1px 2px 0 ${alpha(GREY[500], 0.16)}`,
    `0 1px 2px 0 ${alpha(GREY[500], 0.16)}`,
    `0 1px 2px 0 ${alpha(GREY[500], 0.16)}`,
    `0 1px 2px 0 ${alpha(GREY[500], 0.16)}`,
    `0 1px 2px 0 ${alpha(GREY[500], 0.16)}`,
    `0 1px 2px 0 ${alpha(GREY[500], 0.16)}`,
    `0 1px 2px 0 ${alpha(GREY[500], 0.16)}`,
    `0 1px 2px 0 ${alpha(GREY[500], 0.16)}`,
    `0 1px 2px 0 ${alpha(GREY[500], 0.16)}`,
  ],
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        ":root": { "--font-mono": monoStack },
        body: { backgroundColor: BG_DEFAULT },
        "*::-webkit-scrollbar": { width: 8, height: 8 },
        "*::-webkit-scrollbar-thumb": {
          backgroundColor: alpha(GREY[500], 0.32),
          borderRadius: 4,
        },
        "*::-webkit-scrollbar-track": { backgroundColor: "transparent" },
      },
    },
    MuiTypography: {
      defaultProps: { variantMapping: { money: "span" } },
    },
    MuiCard: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        root: {
          borderRadius: 16,
          backgroundColor: BG_PAPER,
          border: "none",
          backgroundImage: "none",
          boxShadow: `0 0 2px 0 ${alpha(GREY[500], 0.2)}, 0 12px 24px -4px ${alpha(GREY[500], 0.12)}`,
        },
      },
    },
    MuiCardContent: {
      styleOverrides: {
        root: { padding: 24, "&:last-child": { paddingBottom: 24 } },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { borderRadius: 10, textTransform: "none", fontWeight: 700 },
        containedPrimary: {
          color: "#ffffff",
          "&:hover": { backgroundColor: PRIMARY_DARK },
        },
      },
    },
    MuiPaper: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        root: { backgroundImage: "none" },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: { borderColor: alpha(GREY[500], 0.16), borderStyle: "dashed" },
        head: {
          fontWeight: 600,
          fontSize: "0.75rem",
          textTransform: "none",
          letterSpacing: 0,
          color: GREY[600],
          backgroundColor: GREY[100],
        },
      },
    },
    MuiTableRow: {
      styleOverrides: {
        root: {
          "&:last-child td": { borderBottom: 0 },
          "&:hover td": { backgroundColor: GREY[100] },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 700, borderRadius: 6 },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: { backgroundImage: "none" },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: { backgroundImage: "none" },
      },
    },
    MuiTextField: {
      defaultProps: { variant: "outlined", size: "small" },
      styleOverrides: {
        root: {
          "& .MuiOutlinedInput-root": {
            borderRadius: 10,
            "& fieldset": { borderColor: alpha(GREY[500], 0.32) },
            "&:hover fieldset": { borderColor: alpha(GREY[500], 0.6) },
          },
        },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: { borderRadius: 12 },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: GREY[800],
          color: "#ffffff",
          borderRadius: 8,
          fontSize: "0.75rem",
        },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: { borderRadius: 10 },
      },
    },
    MuiPopover: {
      styleOverrides: {
        paper: {
          borderRadius: 12,
          border: `1px solid ${alpha(GREY[500], 0.12)}`,
          boxShadow: `0 20px 40px -4px ${alpha(GREY[500], 0.24)}`,
        },
      },
    },
    MuiMenu: {
      styleOverrides: {
        paper: {
          borderRadius: 12,
          border: `1px solid ${alpha(GREY[500], 0.12)}`,
        },
      },
    },
    MuiBadge: {
      styleOverrides: {
        dot: { borderRadius: "50%" },
      },
    },
  },
});

export const monoFontFamily = monoStack;
