import { useState } from "react";
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
  IconButton,
  Avatar,
  useMediaQuery,
  type Theme,
} from "@mui/material";
import { Menu as MenuIcon } from "@mui/icons-material";
import { NavLink, Route, Routes } from "react-router-dom";
import { routes } from "../../routes";
import HealthBadges from "./HealthBadges";
import NotificationsPopover from "./NotificationsPopover";
import AccountPopover from "./AccountPopover";
import { useAuthStore } from "../../stores/authStore";
import AlertToastSubscriber from "../../pages/alerts/AlertToastSubscriber";

const DRAWER_WIDTH = 280;

const styles = {
  root: { display: "flex", minHeight: "100vh", bgcolor: "background.default" },
  appBar: {
    bgcolor: "rgba(255, 255, 255, 0.85)",
    backdropFilter: "blur(8px)",
    borderBottom: "1px dashed",
    borderColor: "divider",
    boxShadow: "none",
    color: "text.primary",
  },
  drawer: {
    width: DRAWER_WIDTH,
    flexShrink: 0,
    "& .MuiDrawer-paper": {
      width: DRAWER_WIDTH,
      boxSizing: "border-box",
      bgcolor: "background.paper",
      borderRight: "1px dashed",
      borderColor: "divider",
    },
  },
  mobileDrawer: {
    "& .MuiDrawer-paper": {
      width: DRAWER_WIDTH,
      boxSizing: "border-box",
      bgcolor: "background.paper",
    },
  },
  logoBox: {
    display: "flex",
    alignItems: "center",
    gap: 1.5,
    px: 2.5,
    py: 3,
  },
  logoIcon: {
    width: 40,
    height: 40,
    borderRadius: "12px",
    background: "linear-gradient(135deg, #5BE49B 0%, #00A76F 100%)",
    color: "#ffffff",
    fontWeight: 800,
    fontSize: 18,
    boxShadow: "0 4px 12px rgba(0, 167, 111, 0.3)",
  },
  workspaceBox: {
    display: "flex",
    alignItems: "center",
    gap: 1.5,
    mx: 2.5,
    mb: 2,
    p: 1.5,
    borderRadius: "12px",
    bgcolor: "action.hover",
  },
  workspaceAvatar: {
    width: 36,
    height: 36,
    fontSize: 14,
    fontWeight: 700,
    background: "linear-gradient(135deg, #5BE49B, #00A76F)",
    color: "#ffffff",
  },
  navSection: { px: 2, py: 0.5 },
  sectionLabel: {
    px: 1,
    pt: 2,
    pb: 1,
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    color: "text.disabled",
  },
  navItem: {
    borderRadius: "8px",
    mb: 0.5,
    py: 1,
    px: 1.5,
    color: "text.secondary",
    "&.active": {
      bgcolor: "#C8FAD6",
      color: "#00A76F",
      "& .MuiListItemIcon-root": { color: "#00A76F" },
      "& .MuiListItemText-primary": { fontWeight: 600 },
    },
    "&:hover": {
      bgcolor: "action.hover",
    },
  },
  navIcon: { minWidth: 36, color: "inherit" },
  main: {
    flex: 1,
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
  },
  headerToolbar: {
    gap: 1,
    minHeight: { xs: 56, md: 64 },
    px: { xs: 2, md: 3 },
  },
  content: { flex: 1, minWidth: 0, overflow: "auto", bgcolor: "background.default" },
} as const;

const NAV_SECTIONS = [
  {
    label: "Overview",
    items: ["/", "/market"],
  },
  {
    label: "Trading",
    items: ["/bot", "/paper", "/logs"],
  },
  {
    label: "Analysis",
    items: ["/risk", "/backtest", "/ai"],
  },
  {
    label: "System",
    items: ["/alerts", "/settings"],
  },
];

function NavContent() {
  const routeMap = new Map(routes.map((r) => [r.path, r]));

  return (
    <>
      {NAV_SECTIONS.map((section) => (
        <Box key={section.label} sx={styles.navSection}>
          <Typography sx={styles.sectionLabel}>{section.label}</Typography>
          <List disablePadding>
            {section.items.map((path) => {
              const r = routeMap.get(path);
              if (!r) return null;
              const Icon = r.icon;
              return (
                <ListItem key={r.path} disablePadding>
                  <ListItemButton
                    component={NavLink}
                    to={r.path}
                    end={r.path === "/"}
                    sx={styles.navItem}
                  >
                    <ListItemIcon sx={styles.navIcon}>
                      <Icon />
                    </ListItemIcon>
                    <ListItemText
                      primary={r.label}
                      primaryTypographyProps={{ variant: "body2", sx: { fontWeight: 500 } }}
                    />
                  </ListItemButton>
                </ListItem>
              );
            })}
          </List>
        </Box>
      ))}
    </>
  );
}

export default function AppShell() {
  const user = useAuthStore((s) => s.user);
  const [mobileOpen, setMobileOpen] = useState(false);
  const isDesktop = useMediaQuery((t: Theme) => t.breakpoints.up("lg"));

  const drawerContent = (
    <>
      <Box sx={styles.logoBox}>
        <Avatar sx={styles.logoIcon}>TB</Avatar>
        <Box>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, lineHeight: 1.2, color: "text.primary" }}>
            Trading Bot
          </Typography>
          <Typography variant="caption" sx={{ color: "text.disabled" }}>
            v2.0
          </Typography>
        </Box>
      </Box>

      {user && (
        <Box sx={styles.workspaceBox}>
          <Avatar sx={styles.workspaceAvatar}>
            {user.username.charAt(0).toUpperCase()}
          </Avatar>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="subtitle2" noWrap sx={{ color: "text.primary" }}>
              {user.username}
            </Typography>
            <Typography variant="caption" sx={{ color: "text.disabled" }} noWrap>
              {user.role}
            </Typography>
          </Box>
        </Box>
      )}

      <Box sx={{ flex: 1, overflow: "auto" }}>
        <NavContent />
      </Box>
    </>
  );

  return (
    <Box sx={styles.root}>
      <AlertToastSubscriber />

      {isDesktop ? (
        <Drawer variant="permanent" sx={styles.drawer}>
          {drawerContent}
        </Drawer>
      ) : (
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={styles.mobileDrawer}
        >
          {drawerContent}
        </Drawer>
      )}

      <Box sx={styles.main}>
        <AppBar position="sticky" sx={styles.appBar} elevation={0}>
          <Toolbar sx={styles.headerToolbar}>
            {!isDesktop && (
              <IconButton
                onClick={() => setMobileOpen(true)}
                sx={{ color: "text.primary" }}
              >
                <MenuIcon />
              </IconButton>
            )}

            <Typography
              variant="subtitle2"
              sx={{ color: "text.disabled", fontWeight: 500 }}
            >
              paper &middot; BTCUSDT
            </Typography>

            <Box sx={{ flex: 1 }} />

            <HealthBadges />
            <NotificationsPopover />
            <AccountPopover />
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
