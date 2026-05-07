import {
  Box,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  AppBar,
  Typography,
  Button,
} from "@mui/material";
import { NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { routes } from "../../routes";
import HealthBadges from "./HealthBadges";
import { useAuthStore } from "../../stores/authStore";
import AlertToastSubscriber from "../../pages/alerts/AlertToastSubscriber";

const DRAWER_WIDTH = 220;

const styles = {
  root: { display: "flex", minHeight: "100vh", bgcolor: "background.default" },
  appBar: {
    width: "100%",
    bgcolor: "background.paper",
    borderBottom: 1,
    borderColor: "divider",
    boxShadow: "none",
  },
  drawer: {
    width: DRAWER_WIDTH,
    flexShrink: 0,
    "& .MuiDrawer-paper": {
      width: DRAWER_WIDTH,
      boxSizing: "border-box",
      bgcolor: "background.paper",
      borderRight: 1,
      borderColor: "divider",
    },
  },
  brand: {
    px: 2,
    py: 2,
    fontWeight: 700,
    letterSpacing: 0.5,
  },
  navItem: {
    borderRadius: 1,
    mx: 1,
    "&.active": {
      bgcolor: "action.selected",
      color: "primary.main",
      "& .MuiListItemIcon-root": { color: "primary.main" },
    },
  },
  main: {
    flex: 1,
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
  },
  content: { flex: 1, minWidth: 0 },
} as const;

export default function AppShell() {
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);
  const navigate = useNavigate();
  const onLogout = () => {
    clear();
    navigate("/login", { replace: true });
  };
  return (
    <Box sx={styles.root}>
      <AlertToastSubscriber />
      <Drawer variant="permanent" sx={styles.drawer}>
        <Typography sx={styles.brand}>Trading Bot</Typography>
        <List dense>
          {routes.map((r) => {
            const Icon = r.icon;
            return (
              <ListItem key={r.path} disablePadding>
                <ListItemButton
                  component={NavLink}
                  to={r.path}
                  end={r.path === "/"}
                  sx={styles.navItem}
                >
                  <ListItemIcon sx={{ minWidth: 36, color: "text.secondary" }}>
                    <Icon />
                  </ListItemIcon>
                  <ListItemText primary={r.label} />
                </ListItemButton>
              </ListItem>
            );
          })}
        </List>
      </Drawer>
      <Box sx={styles.main}>
        <AppBar position="static" sx={styles.appBar} elevation={0}>
          <Toolbar variant="dense" sx={{ gap: 2 }}>
            <Typography variant="subtitle2" sx={{ color: "text.secondary" }}>
              paper · BTCUSDT
            </Typography>
            <Box sx={{ flex: 1 }} />
            <HealthBadges />
            {user && (
              <>
                <Typography variant="caption" sx={{ color: "text.secondary" }}>
                  {user.username} · {user.role}
                </Typography>
                <Button size="small" onClick={onLogout}>
                  Logout
                </Button>
              </>
            )}
          </Toolbar>
        </AppBar>
        <Box component="main" sx={styles.content}>
          <Routes>
            {routes.map((r) => {
              const El = r.element;
              return <Route key={r.path} path={r.path} element={<El />} />;
            })}
          </Routes>
        </Box>
      </Box>
    </Box>
  );
}
