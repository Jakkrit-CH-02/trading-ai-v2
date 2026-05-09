import { useState, type MouseEvent } from "react";
import {
  Badge,
  Box,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Popover,
  Typography,
  Button,
  Chip,
} from "@mui/material";
import { NotificationsNone as BellIcon } from "@mui/icons-material";
import { useQuery } from "@tanstack/react-query";
import { listAlerts, type Alert } from "../../api/alerts";

const SEVERITY_COLOR: Record<Alert["severity"], "info" | "warning" | "error"> = {
  info: "info",
  warning: "warning",
  critical: "error",
};

const styles = {
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    px: 2.5,
    py: 2,
  },
  list: {
    maxHeight: 360,
    overflow: "auto",
  },
  item: {
    px: 2.5,
    py: 1.5,
    "&:not(:last-child)": {
      borderBottom: 1,
      borderColor: "divider",
    },
  },
  empty: {
    py: 6,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 1,
  },
} as const;

export default function NotificationsPopover() {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const open = Boolean(anchorEl);

  const { data: alerts } = useQuery({
    queryKey: ["alerts"],
    queryFn: listAlerts,
    refetchInterval: 5000,
  });

  const unread = alerts?.filter((a) => !a.read) ?? [];

  const handleOpen = (e: MouseEvent<HTMLElement>) => setAnchorEl(e.currentTarget);
  const handleClose = () => setAnchorEl(null);

  return (
    <>
      <IconButton onClick={handleOpen} sx={{ color: "text.secondary" }}>
        <Badge badgeContent={unread.length} color="error" max={99}>
          <BellIcon />
        </Badge>
      </IconButton>

      <Popover
        open={open}
        anchorEl={anchorEl}
        onClose={handleClose}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{ paper: { sx: { width: 360, mt: 1.5 } } }}
      >
        <Box sx={styles.header}>
          <Box>
            <Typography variant="subtitle1">Notifications</Typography>
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              {unread.length > 0
                ? `You have ${unread.length} unread`
                : "All caught up"}
            </Typography>
          </Box>
          {unread.length > 0 && (
            <Button size="small" sx={{ fontWeight: 600 }}>
              Mark all read
            </Button>
          )}
        </Box>

        <Divider />

        {!alerts || alerts.length === 0 ? (
          <Box sx={styles.empty}>
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              No notifications yet
            </Typography>
          </Box>
        ) : (
          <List disablePadding sx={styles.list}>
            {alerts.slice(0, 8).map((alert) => (
              <ListItem key={alert.id} disablePadding sx={styles.item}>
                <ListItemText
                  primary={
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
                      <Chip
                        label={alert.severity}
                        color={SEVERITY_COLOR[alert.severity]}
                        size="small"
                        sx={{ height: 22, fontSize: 11, fontWeight: 700 }}
                      />
                      {!alert.read && (
                        <Box
                          sx={{
                            width: 8,
                            height: 8,
                            borderRadius: "50%",
                            bgcolor: "info.main",
                          }}
                        />
                      )}
                    </Box>
                  }
                  secondary={alert.message}
                  secondaryTypographyProps={{
                    variant: "body2",
                    sx: {
                      color: alert.read ? "text.disabled" : "text.secondary",
                      display: "-webkit-box",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                    },
                  }}
                />
              </ListItem>
            ))}
          </List>
        )}
      </Popover>
    </>
  );
}
