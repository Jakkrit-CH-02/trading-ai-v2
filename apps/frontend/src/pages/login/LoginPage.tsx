import { useState, type FormEvent } from "react";
import { useNavigate, useLocation, Navigate } from "react-router-dom";
import {
  Box,
  Button,
  TextField,
  Typography,
  Alert,
  Avatar,
} from "@mui/material";
import { login, register } from "../../api/auth";
import { useAuthStore } from "../../stores/authStore";

const styles = {
  root: {
    minHeight: "100vh",
    display: "flex",
    bgcolor: "#f9fafb",
  },
  leftPanel: {
    display: { xs: "none", md: "flex" },
    flex: 1,
    flexDirection: "column",
    justifyContent: "center",
    alignItems: "center",
    p: 6,
    background: "linear-gradient(135deg, #C8FAD6 0%, #f9fafb 100%)",
  },
  rightPanel: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    p: { xs: 3, md: 6 },
    bgcolor: "#ffffff",
  },
  formWrapper: { width: "100%", maxWidth: 420 },
  logoBox: {
    display: "flex",
    alignItems: "center",
    gap: 1.5,
    mb: 5,
  },
  logoAvatar: {
    width: 44,
    height: 44,
    borderRadius: "12px",
    background: "linear-gradient(135deg, #5BE49B 0%, #00A76F 100%)",
    color: "#ffffff",
    fontWeight: 800,
    fontSize: 18,
    boxShadow: "0 4px 12px rgba(0, 167, 111, 0.3)",
  },
  field: { mb: 2.5 },
  switchBtn: { mt: 2 },
} as const;

export default function LoginPage() {
  const token = useAuthStore((s) => s.token);
  const setSession = useAuthStore((s) => s.setSession);
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (token) {
    return <Navigate to={from} replace />;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "register") {
        await register(username, password, "admin");
      }
      const res = await login(username, password);
      setSession(res.token, res.user);
      navigate(from, { replace: true });
    } catch (err) {
      const msg =
        err && typeof err === "object" && "message" in err
          ? String((err as { message: unknown }).message)
          : "Login failed";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Box sx={styles.root}>
      <Box sx={styles.leftPanel}>
        <Typography
          variant="h3"
          sx={{ maxWidth: 480, textAlign: "center", mb: 2 }}
        >
          Hi, Welcome back
        </Typography>
        <Typography
          variant="body1"
          sx={{ color: "text.secondary", maxWidth: 400, textAlign: "center" }}
        >
          Manage your automated trading strategies with real-time monitoring and
          AI-powered insights.
        </Typography>
      </Box>

      <Box sx={styles.rightPanel}>
        <Box sx={styles.formWrapper}>
          <Box sx={styles.logoBox}>
            <Avatar sx={styles.logoAvatar}>TB</Avatar>
            <Typography variant="h5" sx={{ fontWeight: 700 }}>
              Trading Bot
            </Typography>
          </Box>

          <Typography variant="h4" sx={{ mb: 1 }}>
            {mode === "login" ? "Sign in" : "Get started"}
          </Typography>
          <Typography variant="body2" sx={{ color: "text.secondary", mb: 4 }}>
            {mode === "login"
              ? "Enter your credentials to continue"
              : "Create an admin account to get started"}
          </Typography>

          {error && (
            <Alert severity="error" sx={{ mb: 3 }}>
              {error}
            </Alert>
          )}

          <Box component="form" onSubmit={onSubmit}>
            <TextField
              label="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              fullWidth
              autoFocus
              sx={styles.field}
              inputProps={{ "aria-label": "username" }}
            />
            <TextField
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              fullWidth
              sx={styles.field}
              inputProps={{ "aria-label": "password" }}
            />
            <Button
              type="submit"
              variant="contained"
              fullWidth
              size="large"
              disabled={submitting || !username || !password}
              sx={{ py: 1.5, fontSize: "1rem" }}
            >
              {submitting
                ? "Please wait..."
                : mode === "login"
                  ? "Sign in"
                  : "Register & sign in"}
            </Button>
          </Box>

          <Button
            fullWidth
            size="small"
            sx={styles.switchBtn}
            onClick={() => {
              setError(null);
              setMode(mode === "login" ? "register" : "login");
            }}
          >
            {mode === "login"
              ? "Need an account? Register"
              : "Have an account? Sign in"}
          </Button>
        </Box>
      </Box>
    </Box>
  );
}
