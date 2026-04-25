import { useT, useThemeMode } from "../theme";
import { PageHeader, Card, Btn } from "../components/Shell";
import { getCurrentUser, signOut } from "../auth";

export function SettingsPage() {
  const t = useT();
  const { mode, setMode } = useThemeMode();
  const user = getCurrentUser();
  const darkMode = mode === "dark";

  const handleLogout = () => {
    signOut();
  };

  return (
    <>
      <PageHeader
        eyebrow="Account"
        title="Settings"
        subtitle="Manage your account and application preferences."
      />
      <div style={{ padding: "24px 34px 40px", maxWidth: 600 }}>
        <Card
          title="Session"
          subtitle={`You are currently signed in as ${user?.displayName ?? "this user"}`}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div>
              <div style={{ fontSize: 13, fontWeight: 500, color: t.ink }}>
                {user?.email || user?.displayName || "Signed in user"}
              </div>
              <div style={{ fontSize: 11, color: t.ink4, marginTop: 2 }}>
                Role: {user?.role ?? "Reviewer"} &middot; SoD enforced
              </div>
            </div>
            <Btn variant="outline" onClick={handleLogout}>
              Sign out
            </Btn>
          </div>
        </Card>

        <div style={{ height: 14 }} />

        <Card title="Appearance" subtitle="Interface color mode">
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 16,
            }}
          >
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: t.ink }}>
                Dark mode
              </div>
              <div style={{ fontSize: 11, color: t.ink4, marginTop: 2 }}>
                {darkMode ? "Dark Government theme is active" : "Modern Government theme is active"}
              </div>
            </div>
            <button
              onClick={() => setMode(darkMode ? "light" : "dark")}
              aria-label="Toggle dark mode"
              style={{
                width: 48,
                height: 26,
                borderRadius: 13,
                border: `1px solid ${darkMode ? t.accent : t.line}`,
                background: darkMode ? t.accentBg : t.surfaceAlt,
                position: "relative",
                cursor: "pointer",
                transition: "background 200ms, border 200ms",
              }}
            >
              <span
                style={{
                  width: 20,
                  height: 20,
                  borderRadius: 10,
                  background: darkMode ? t.accent : t.primary,
                  position: "absolute",
                  top: 2,
                  left: darkMode ? 23 : 3,
                  transition: "left 200ms, background 200ms",
                  boxShadow: "0 1px 4px rgba(0,0,0,0.28)",
                }}
              />
            </button>
          </div>
        </Card>

        <div style={{ height: 14 }} />

        <Card title="About" subtitle="System information">
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "120px 1fr",
              gap: "8px 16px",
              fontSize: 12,
              color: t.ink2,
            }}
          >
            <span style={{ color: t.ink4, fontFamily: t.mono, fontSize: 11 }}>
              Version
            </span>
            <span>POC v0.1</span>
            <span style={{ color: t.ink4, fontFamily: t.mono, fontSize: 11 }}>
              Region
            </span>
            <span>us-east-1</span>
            <span style={{ color: t.ink4, fontFamily: t.mono, fontSize: 11 }}>
              Model
            </span>
            <span>Amazon Nova Lite / Pro</span>
            <span style={{ color: t.ink4, fontFamily: t.mono, fontSize: 11 }}>
              Auth
            </span>
            <span>Cognito (test accounts)</span>
          </div>
        </Card>
      </div>
    </>
  );
}
