import { Route, Routes } from "react-router-dom";
import AppShell from "./components/layout/AppShell";
import LoginPage from "./pages/login/LoginPage";
import RouteGuard from "./components/RouteGuard";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/*"
        element={
          <RouteGuard>
            <AppShell />
          </RouteGuard>
        }
      />
    </Routes>
  );
}
