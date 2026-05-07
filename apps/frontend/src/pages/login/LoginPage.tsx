import { useState, type FormEvent } from "react";
import { useNavigate, useLocation, Navigate } from "react-router-dom";
import { Box, Button, Paper, TextField, Typography, Alert } from "@mui/material";
import { login, register } from "../../api/auth";
import { useAuthStore } from "../../stores/authStore";

const styles = {
  root: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    bgcolor: "background.default",
    p: 2,
  },
  paper: { p: 4, width: "100%", maxWidth: 380 },
  title: { mb: 1, fontWeight: 600 },
  sub: { mb: 3, color: "text.secondary" },
  field: { mb: 2 },
  switchBtn: { mt: 1 },
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
      const msg = err instanceof Error ? err.message : "Login failed";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Box sx={styles.root}>
      <Paper sx={styles.paper} elevation={3}>
        <Typography variant="h5" sx={styles.title}>
          Trading Bot
        </Typography>
        <Typography variant="body2" sx={styles.sub}>
          {mode === "login" ? "Sign in to continue" : "Create an admin account"}
        </Typography>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
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
            disabled={submitting || !username || !password}
          >
            {submitting
              ? "Please wait…"
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
      </Paper>
    </Box>
  );
}
