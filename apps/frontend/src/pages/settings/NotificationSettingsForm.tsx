import {
  Box,
  FormControlLabel,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import type { Settings } from "../../api/settings";

export interface NotificationSettingsFormProps {
  value: Settings;
  errors: Partial<Record<keyof Settings, string>>;
  onChange: (patch: Partial<Settings>) => void;
}

const styles = {
  hint: { color: "text.secondary", mb: 1 },
  row: { display: "flex", flexDirection: { xs: "column", md: "row" }, gap: 2 },
  webhook: { flex: 1 },
} as const;

export default function NotificationSettingsForm(
  props: NotificationSettingsFormProps,
) {
  const { value, errors, onChange } = props;
  return (
    <Stack spacing={1.5}>
      <Typography variant="body2" sx={styles.hint}>
        Where to deliver risk and order alerts.
      </Typography>
      <Box sx={styles.row}>
        <FormControlLabel
          control={
            <Switch
              checked={value.notify_email}
              onChange={(e) => onChange({ notify_email: e.target.checked })}
              inputProps={{ "aria-label": "notify email" }}
            />
          }
          label="Email alerts"
        />
        <TextField
          label="Webhook URL"
          value={value.notify_webhook_url}
          onChange={(e) => onChange({ notify_webhook_url: e.target.value })}
          error={Boolean(errors.notify_webhook_url)}
          helperText={
            errors.notify_webhook_url ?? "Optional. Slack/Discord/etc."
          }
          sx={styles.webhook}
          placeholder="https://hooks.example.com/..."
          inputProps={{ "aria-label": "notify webhook url" }}
        />
      </Box>
    </Stack>
  );
}
