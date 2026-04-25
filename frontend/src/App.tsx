import { BrowserRouter, Routes, Route, Navigate, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { ThemeCtx, ThemeModeCtx, THEME, DARK_THEME } from "./theme";
import { Shell } from "./components/Shell";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { QueuePage } from "./pages/QueuePage";
import { UploadPage } from "./pages/UploadPage";
import { ReviewPage } from "./pages/ReviewPage";
import { AuditPage } from "./pages/AuditPage";
import { AuditOverviewPage } from "./pages/AuditOverviewPage";
import { SettingsPage } from "./pages/SettingsPage";
import { hasAuthSession, isAuthRequired } from "./auth";

function RequireAuth({ children }: { children: ReactNode }) {
  if (isAuthRequired && !hasAuthSession()) {
    return <Navigate to="/" replace />;
  }
  return children;
}

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
      {page === "queue" && <QueuePage />}
      {page === "upload" && <UploadPage />}
      {page === "audit" && <AuditOverviewPage />}
      {page === "settings" && <SettingsPage />}
    </Shell>
  );
}

function App() {
  const [themeMode, setThemeMode] = useState<"light" | "dark">(() => {
    return localStorage.getItem("msbn.theme") === "dark" ? "dark" : "light";
  });
  const theme = themeMode === "dark" ? DARK_THEME : THEME;
  const themeModeValue = useMemo(
    () => ({
      mode: themeMode,
      setMode: (mode: "light" | "dark") => {
        localStorage.setItem("msbn.theme", mode);
        setThemeMode(mode);
      },
    }),
    [themeMode]
  );

  return (
    <ThemeCtx.Provider value={theme}>
      <ThemeModeCtx.Provider value={themeModeValue}>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<LoginPage />} />
            <Route path="/dashboard" element={<RequireAuth><ShellRoute page="dashboard" /></RequireAuth>} />
            <Route path="/queue" element={<RequireAuth><ShellRoute page="queue" /></RequireAuth>} />
            <Route path="/upload" element={<RequireAuth><ShellRoute page="upload" /></RequireAuth>} />
            <Route path="/settings" element={<RequireAuth><ShellRoute page="settings" /></RequireAuth>} />
            <Route path="/audit" element={<RequireAuth><ShellRoute page="audit" /></RequireAuth>} />
            <Route path="/review/:id" element={<RequireAuth><ErrorBoundary><ReviewPage /></ErrorBoundary></RequireAuth>} />
            <Route path="/audit/:id" element={<RequireAuth><AuditPage /></RequireAuth>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ThemeModeCtx.Provider>
    </ThemeCtx.Provider>
  );
}

export default App;
