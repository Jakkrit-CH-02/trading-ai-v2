import { useState, type MouseEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  Avatar,
  Box,
  Divider,
  IconButton,
  MenuItem,
  MenuList,
  Popover,
  Typography,
} from "@mui/material";
import { useAuthStore } from "../../stores/authStore";

const styles = {
  avatar: {
    width: 36,
    height: 36,
    fontSize: 14,
    fontWeight: 700,
    background: "linear-gradient(135deg, #5BE49B, #00A76F)",
    color: "#ffffff",
    cursor: "pointer",
    transition: "opacity 0.2s",
    "&:hover": { opacity: 0.8 },
  },
  header: { px: 2.5, py: 2 },
  menuItem: {
    py: 1,
    px: 2.5,
    borderRadius: "8px",
    mx: 1,
    typography: "body2",
    color: "text.secondary",
    "&:hover": { color: "text.primary" },
  },
  logoutItem: {
    py: 1,
    px: 2.5,
    borderRadius: "8px",
    mx: 1,
    mb: 1,
    typography: "body2",
    color: "error.main",
    fontWeight: 600,
  },
} as const;

export default function AccountPopover() {
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);
  const navigate = useNavigate();
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const open = Boolean(anchorEl);

  const handleOpen = (e: MouseEvent<HTMLElement>) => setAnchorEl(e.currentTarget);
  const handleClose = () => setAnchorEl(null);

  const handleLogout = () => {
    handleClose();
    clear();
    navigate("/login", { replace: true });
  };

  const handleNav = (path: string) => {
    handleClose();
    navigate(path);
  };

  if (!user) return null;

  return (
    <>
      <IconButton onClick={handleOpen} sx={{ p: 0 }}>
        <Avatar sx={styles.avatar}>
          {user.username.charAt(0).toUpperCase()}
        </Avatar>
      </IconButton>

      <Popover
        open={open}
        anchorEl={anchorEl}
        onClose={handleClose}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{ paper: { sx: { width: 220, mt: 1.5 } } }}
      >
        <Box sx={styles.header}>
          <Typography variant="subtitle2">{user.username}</Typography>
          <Typography variant="body2" sx={{ color: "text.disabled" }}>
            {user.role}
          </Typography>
        </Box>

        <Divider sx={{ borderStyle: "dashed" }} />

        <MenuList disablePadding sx={{ py: 1 }}>
          <MenuItem sx={styles.menuItem} onClick={() => handleNav("/")}>
            Dashboard
          </MenuItem>
          <MenuItem sx={styles.menuItem} onClick={() => handleNav("/settings")}>
            Settings
          </MenuItem>
        </MenuList>

        <Divider sx={{ borderStyle: "dashed" }} />

        <MenuList disablePadding sx={{ py: 1 }}>
          <MenuItem sx={styles.logoutItem} onClick={handleLogout}>
            Logout
          </MenuItem>
        </MenuList>
      </Popover>
    </>
  );
}
