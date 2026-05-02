import { Box, Typography } from "@mui/material";
import BuildDatasetSection from "./BuildDatasetSection";
import ComputeFeaturesSection from "./ComputeFeaturesSection";
import ModelListSection from "./ModelListSection";
import PredictExplainSection from "./PredictExplainSection";
import TrainingRunSection from "./TrainingRunSection";

const styles = {
  root: { p: 3, display: "flex", flexDirection: "column", gap: 3 },
} as const;

export default function AITrainingPage() {
  return (
    <Box sx={styles.root}>
      <Typography variant="h5">AI Training</Typography>
      <BuildDatasetSection />
      <ComputeFeaturesSection />
      <TrainingRunSection />
      <ModelListSection />
      <PredictExplainSection />
    </Box>
  );
}
