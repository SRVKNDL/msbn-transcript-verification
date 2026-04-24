import { useT, useThemeMode } from "../theme";
import { PageHeader, Card, Btn } from "../components/Shell";
import { signOut } from "../auth";

export function SettingsPage() {
  const t = useT();
  const { mode, setMode } = useThemeMode();
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
        <Card title="Session" subtitle="You are currently signed in as S. Pant">
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div>
              <div style={{ fontSize: 13, fontWeight: 500, color: t.ink }}>
                s.pant@msbn.ms.gov
              </div>
              <div style={{ fontSize: 11, color: t.ink4, marginTop: 2 }}>
                Role: Reviewer &middot; SoD enforced
              </div>
            </div>
            <Btn variant="outline" onClick={handleLogout}>
              Sign out
            </Btn>
          </div>
        </Card>

        <div style={{ height: 14 }} />

        <Card title="Appearance" subtitle="Visual preferences">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 500, color: t.ink }}>Dark mode</div>
              <div style={{ fontSize: 11, color: t.ink4, marginTop: 2 }}>
                Use a softer low-glare theme across the dashboard
              </div>
            </div>
            <button
              onClick={() => setMode(darkMode ? "light" : "dark")}
              style={{
                width: 44, height: 24, borderRadius: 12, border: "none",
                background: darkMode ? t.accent : t.line,
                position: "relative", cursor: "pointer",
                transition: "background 200ms",
              }}
            >
              <div style={{
                width: 18, height: 18, borderRadius: 9,
                background: "#fff", position: "absolute", top: 3,
                left: darkMode ? 23 : 3, transition: "left 200ms",
                boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
              }} />
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
