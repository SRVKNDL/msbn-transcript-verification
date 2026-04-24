import { useT } from "../theme";
import { MOCK_APPLICATIONS } from "../mock-data";

interface ShellProps {
  page: string;
  onNavigate: (id: string) => void;
  children: React.ReactNode;
}

export function Shell({ page, onNavigate, children }: ShellProps) {
  const t = useT();

  const pendingCount = MOCK_APPLICATIONS.filter((a) => a.status === "READY_FOR_REVIEW").length;

  const navItems = [
    { id: "dashboard", label: "Dashboard", icon: "\u25ce" },
    { id: "queue", label: "Review queue", icon: "\u25a4", badge: pendingCount },
    { id: "upload", label: "Upload transcript", icon: "\u21a5" },
    { id: "audit", label: "Audit log", icon: "\u2261" },
    { id: "settings", label: "Settings", icon: "\u2726" },
  ];

  return (
    <div
      style={{
        width: "100%",
        height: "100vh",
        background: t.bg,
        color: t.ink,
        fontFamily: t.sans,
        display: "grid",
        gridTemplateColumns: "220px 1fr",
        gridTemplateRows: "60px 1fr",
        overflow: "hidden",
      }}
    >
      {/* Top bar */}
      <div
        style={{
          gridColumn: "1 / -1",
          background: t.primary,
          color: t.primaryInk,
          display: "flex",
          alignItems: "center",
          padding: "0 22px",
          gap: 16,
          borderBottom: `3px solid ${t.accent}`,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div
            style={{
              width: 30,
              height: 30,
              borderRadius: "50%",
              border: `1.5px solid ${t.primaryInk}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: 0.5,
              fontFamily: t.mono,
            }}
          >
            MS
          </div>
          <div>
            <div
              style={{
                fontSize: 10,
                opacity: 0.75,
                letterSpacing: 1,
                textTransform: "uppercase",
              }}
            >
              Mississippi Board of Nursing
            </div>
            <div
              style={{ fontSize: 14, fontWeight: 600, fontFamily: t.serif }}
            >
              Transcript Verification
            </div>
          </div>
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ fontSize: 12, opacity: 0.85 }}>S. Pant</div>
        <div
          style={{
            width: 30,
            height: 30,
            borderRadius: 15,
            background: "rgba(255,255,255,0.15)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 11,
            fontWeight: 600,
          }}
        >
          SP
        </div>
      </div>

      {/* Sidebar */}
      <div
        style={{
          background: t.surface,
          borderRight: `1px solid ${t.line}`,
          padding: "18px 0",
          display: "flex",
          flexDirection: "column",
          gap: 2,
        }}
      >
        {navItems.map((item) => {
          const active = item.id === page;
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "9px 22px",
                border: "none",
                cursor: "pointer",
                background: active ? t.surfaceAlt : "transparent",
                color: active ? t.primary : t.ink2,
                fontSize: 13,
                fontWeight: active ? 600 : 500,
                fontFamily: "inherit",
                textAlign: "left",
                borderLeft: `3px solid ${active ? t.accent : "transparent"}`,
                marginLeft: -1,
              }}
            >
              <span
                style={{
                  width: 14,
                  color: active ? t.accent : t.ink3,
                  fontSize: 13,
                }}
              >
                {item.icon}
              </span>
              <span style={{ flex: 1 }}>{item.label}</span>
              {item.badge != null && (
                <span
                  style={{
                    background: t.accent,
                    color: t.primaryInk,
                    fontSize: 10,
                    fontWeight: 700,
                    padding: "1px 6px",
                    borderRadius: 8,
                    fontFamily: t.mono,
                  }}
                >
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
        <div style={{ flex: 1 }} />
        <div
          style={{
            padding: "12px 22px",
            fontSize: 10,
            color: t.ink4,
            fontFamily: t.mono,
            letterSpacing: 0.3,
          }}
        >
          POC v0.1 · build 2026-04-21
        </div>
      </div>

      {/* Main content */}
      <div style={{ overflow: "auto" }}>{children}</div>
    </div>
  );
}

// Reusable sub-components used by pages inside the shell

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}) {
  const t = useT();
  return (
    <div
      style={{
        padding: "26px 34px 20px",
        borderBottom: `1px solid ${t.line}`,
        background: t.surface,
        display: "flex",
        alignItems: "flex-end",
        gap: 16,
      }}
    >
      <div style={{ flex: 1 }}>
        {eyebrow && (
          <div
            style={{
              fontSize: 11,
              color: t.ink4,
              letterSpacing: 0.6,
              textTransform: "uppercase",
              marginBottom: 6,
              fontFamily: t.mono,
            }}
          >
            {eyebrow}
          </div>
        )}
        <div
          style={{
            fontSize: 26,
            fontWeight: 600,
            fontFamily: t.serif,
            letterSpacing: -0.3,
            color: t.ink,
          }}
        >
          {title}
        </div>
        {subtitle && (
          <div style={{ fontSize: 13, color: t.ink3, marginTop: 4 }}>
            {subtitle}
          </div>
        )}
      </div>
      {actions}
    </div>
  );
}

export function Card({
  title,
  subtitle,
  children,
  actions,
  pad = 20,
}: {
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
  pad?: number;
}) {
  const t = useT();
  return (
    <div
      style={{
        background: t.surface,
        border: `1px solid ${t.line}`,
        borderRadius: 4,
        overflow: "hidden",
      }}
    >
      {(title || actions) && (
        <div
          style={{
            padding: "14px 18px",
            borderBottom: `1px solid ${t.line2}`,
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <div style={{ flex: 1 }}>
            <div
              style={{
                fontSize: 14,
                fontWeight: 600,
                fontFamily: t.serif,
                color: t.ink,
              }}
            >
              {title}
            </div>
            {subtitle && (
              <div style={{ fontSize: 11, color: t.ink4, marginTop: 2 }}>
                {subtitle}
              </div>
            )}
          </div>
          {actions}
        </div>
      )}
      <div style={{ padding: pad }}>{children}</div>
    </div>
  );
}

export function Btn({
  children,
  variant = "primary",
  size = "md",
  onClick,
  disabled,
}: {
  children: React.ReactNode;
  variant?: "primary" | "accent" | "ghost" | "outline";
  size?: "sm" | "md" | "lg";
  onClick?: () => void;
  disabled?: boolean;
}) {
  const t = useT();
  const pad = size === "sm" ? "5px 11px" : size === "lg" ? "10px 20px" : "7px 14px";
  const fs = size === "sm" ? 12 : size === "lg" ? 14 : 13;
  const styles = {
    primary: { bg: t.primary, fg: t.primaryInk, border: t.primary },
    accent: { bg: t.accent, fg: t.primaryInk, border: t.accent },
    ghost: { bg: "transparent", fg: t.ink2, border: t.line },
    outline: { bg: t.surface, fg: t.primary, border: t.primary },
  }[variant];

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        background: disabled ? t.line2 : styles.bg,
        color: disabled ? t.ink4 : styles.fg,
        border: `1px solid ${disabled ? t.line : styles.border}`,
        padding: pad,
        fontSize: fs,
        fontWeight: 600,
        fontFamily: "inherit",
        borderRadius: 3,
        cursor: disabled ? "not-allowed" : "pointer",
        letterSpacing: 0.1,
      }}
    >
      {children}
    </button>
  );
}
