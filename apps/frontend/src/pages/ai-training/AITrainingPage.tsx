import { Box, Typography } from "@mui/material";
import BuildDatasetSection from "./BuildDatasetSection";
import ComputeFeaturesSection from "./ComputeFeaturesSection";

const styles = {
  root: { p: 3, display: "flex", flexDirection: "column", gap: 3 },
} as const;

export default function AITrainingPage() {
  return (
    <Box sx={styles.root}>
      <Typography variant="h5">AI Training</Typography>
      <BuildDatasetSection />
      <ComputeFeaturesSection />
    </Box>
  );
}
