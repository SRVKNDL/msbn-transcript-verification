import { useEffect, useRef, useState } from "react";
import { useT, useThemeMode } from "../theme";
import { listApplications } from "../api";
import { getCurrentUser, signOut } from "../auth";

interface ShellProps {
  page: string;
  onNavigate: (id: string) => void;
  children: React.ReactNode;
}

export function Shell({ page, onNavigate, children }: ShellProps) {
  const t = useT();
  const { mode, setMode } = useThemeMode();
  const [pendingCount, setPendingCount] = useState(0);
  const [profileOpen, setProfileOpen] = useState(false);
  const profileMenuRef = useRef<HTMLDivElement>(null);
  const user = getCurrentUser();
  const darkMode = mode === "dark";

  useEffect(() => {
    listApplications({ statuses: ["READY_FOR_REVIEW"] })
      .then((apps) =>
        setPendingCount(
          apps.filter(
            (a) =>
              a.status === "READY_FOR_REVIEW" &&
              Boolean(a.applicantName.trim() || a.institution.trim())
          ).length
        )
      )
      .catch(() => setPendingCount(0));
  }, []);

  useEffect(() => {
    if (!profileOpen) return;
    const handleClick = (event: MouseEvent) => {
      if (!profileMenuRef.current?.contains(event.target as Node)) {
        setProfileOpen(false);
      }
    };
    window.addEventListener("mousedown", handleClick);
    return () => window.removeEventListener("mousedown", handleClick);
  }, [profileOpen]);

  const navItems = [
    { id: "dashboard", label: "Dashboard", icon: "\u25ce" },
    { id: "queue", label: "Review queue", icon: "\u25a4", badge: pendingCount },
    { id: "upload", label: "Upload transcript", icon: "\u21a5" },
    { id: "audit", label: "Audit log", icon: "\u2261" },
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
              borderRadius: 6,
              background: "#2563eb",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: 0.5,
              fontFamily: t.mono,
              color: "#fff",
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
        <div ref={profileMenuRef} style={{ position: "relative" }}>
          <button
            onClick={() => setProfileOpen((open) => !open)}
            style={{
              border: "none",
              background: "transparent",
              color: "inherit",
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: 0,
              cursor: "pointer",
              fontFamily: "inherit",
            }}
          >
            <span style={{ fontSize: 12, opacity: 0.85 }}>
              {user?.displayName ?? "Signed in"}
            </span>
            <span
              style={{
                width: 30,
                height: 30,
                borderRadius: 15,
                background: "rgba(255,255,255,0.15)",
                border: "1px solid rgba(255,255,255,0.22)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 11,
                fontWeight: 600,
              }}
            >
              {user?.initials ?? "U"}
            </span>
          </button>

          {profileOpen && (
            <div
              style={{
                position: "absolute",
                top: 42,
                right: 0,
                width: 260,
                background: t.surface,
                color: t.ink,
                border: `1px solid ${t.line}`,
                borderTop: `3px solid ${t.accent}`,
                borderRadius: 3,
                boxShadow: "0 18px 45px rgba(0,0,0,0.32)",
                zIndex: 20,
                padding: 10,
              }}
            >
              <div
                style={{
                  padding: "8px 10px 12px",
                  borderBottom: `1px solid ${t.line2}`,
                  marginBottom: 6,
                }}
              >
                <div style={{ fontSize: 13, fontWeight: 600 }}>
                  {user?.displayName ?? "Signed in"}
                </div>
                <div style={{ fontSize: 11, color: t.ink4, marginTop: 3 }}>
                  {user?.email ?? "Reviewer account"}
                </div>
              </div>

              <button
                onClick={() => {
                  setProfileOpen(false);
                  onNavigate("settings");
                }}
                style={{
                  width: "100%",
                  border: "none",
                  background: "transparent",
                  color: t.ink2,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "9px 10px",
                  borderRadius: 3,
                  cursor: "pointer",
                  fontFamily: "inherit",
                  fontSize: 13,
                  textAlign: "left",
                }}
              >
                <span>Settings</span>
                <span style={{ color: t.ink4, fontFamily: t.mono, fontSize: 11 }}>
                  &rarr;
                </span>
              </button>

              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "9px 10px",
                  color: t.ink2,
                  fontSize: 13,
                }}
              >
                <span>{darkMode ? "Dark mode" : "Light mode"}</span>
                <button
                  onClick={() => setMode(darkMode ? "light" : "dark")}
                  aria-label="Toggle dark mode"
                  style={{
                    width: 44,
                    height: 24,
                    borderRadius: 12,
                    border: `1px solid ${darkMode ? t.accent : t.line}`,
                    background: darkMode ? t.accentBg : t.surfaceAlt,
                    position: "relative",
                    cursor: "pointer",
                    transition: "background 200ms, border 200ms",
                  }}
                >
                  <span
                    style={{
                      width: 18,
                      height: 18,
                      borderRadius: 9,
                      background: darkMode ? t.accent : t.primary,
                      position: "absolute",
                      top: 2,
                      left: darkMode ? 22 : 2,
                      transition: "left 200ms, background 200ms",
                      boxShadow: "0 1px 4px rgba(0,0,0,0.35)",
                    }}
                  />
                </button>
              </div>

              <button
                onClick={signOut}
                style={{
                  width: "100%",
                  border: "none",
                  borderTop: `1px solid ${t.line2}`,
                  background: "transparent",
                  color: t.high,
                  padding: "11px 10px 8px",
                  marginTop: 5,
                  cursor: "pointer",
                  fontFamily: "inherit",
                  fontSize: 13,
                  textAlign: "left",
                }}
              >
                Sign out
              </button>
            </div>
          )}
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
        <div
          style={{
            padding: "0 18px 10px",
            fontSize: 10,
            color: t.ink4,
            letterSpacing: 0.8,
            textTransform: "uppercase",
            fontFamily: t.mono,
          }}
        >
          Navigation
        </div>
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
                padding: "9px 18px",
                margin: "0 10px",
                border: "none",
                cursor: "pointer",
                background: active ? t.accentBg : "transparent",
                color: active ? t.primary : t.ink2,
                fontSize: 13,
                fontWeight: active ? 600 : 500,
                fontFamily: "inherit",
                textAlign: "left",
                borderRadius: 6,
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
        borderRadius: 8,
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
