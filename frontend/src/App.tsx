import { BrowserRouter, Routes, Route, Navigate, useNavigate } from "react-router-dom";
import { ThemeCtx, THEME } from "./theme";
import { Shell } from "./components/Shell";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { QueuePage } from "./pages/QueuePage";
import { UploadPage } from "./pages/UploadPage";
import { ReviewPage } from "./pages/ReviewPage";
import { AuditPage } from "./pages/AuditPage";
import { AuditOverviewPage } from "./pages/AuditOverviewPage";
import { SettingsPage } from "./pages/SettingsPage";

// Pages inside Shell share the same sidebar routing.
function ShellRoute({ page }: { page: string }) {
  const navigate = useNavigate();

  const handleNavigate = (id: string) => {
    const routes: Record<string, string> = {
      dashboard: "/dashboard",
      queue: "/queue",
      upload: "/upload",
      audit: "/audit",
      settings: "/settings",
    };
    navigate(routes[id] ?? "/dashboard");
  };

  return (
    <Shell page={page} onNavigate={handleNavigate}>
      {page === "dashboard" && <DashboardPage onNavigate={handleNavigate} />}
      {page === "upload" && <UploadPage />}
      {page === "audit" && <AuditOverviewPage />}
      {page === "settings" && <SettingsPage />}
    </Shell>
  );
}

function App() {
  return (
    <ThemeCtx.Provider value={THEME}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LoginPage />} />
          <Route path="/dashboard" element={<ShellRoute page="dashboard" />} />
          <Route path="/queue" element={<QueuePage />} />
          <Route path="/upload" element={<ShellRoute page="upload" />} />
          <Route path="/settings" element={<ShellRoute page="settings" />} />
          <Route path="/audit" element={<ShellRoute page="audit" />} />
          <Route path="/review/:id" element={<ReviewPage />} />
          <Route path="/audit/:id" element={<AuditPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </ThemeCtx.Provider>
  );
}

export default App;
