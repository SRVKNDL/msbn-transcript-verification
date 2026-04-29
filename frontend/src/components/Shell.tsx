import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useT, useThemeMode } from "../theme";
import { listApplications } from "../api";
import { getCurrentUser, signOut } from "../auth";
import { useViewport } from "../useViewport";
import type { Application } from "../types";
import {
  APP_ROUTES,
  applicationAuditPath,
  applicationReviewPath,
  detailBackStateFor,
  isApplicationReviewable,
  sourceFromSection,
} from "../navigation";

interface ShellProps {
  page: string;
  onNavigate: (id: string) => void;
  children: React.ReactNode;
  mode?: "standard" | "detail";
  contentOverflow?: "auto" | "hidden";
}

export function Shell({
  page,
  onNavigate,
  children,
  mode: shellMode = "standard",
  contentOverflow = "auto",
}: ShellProps) {
  const t = useT();
  const navigate = useNavigate();
  const { mode, setMode } = useThemeMode();
  const [pendingCount, setPendingCount] = useState(0);
  const [searchApps, setSearchApps] = useState<Application[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(shellMode !== "detail");
  const profileMenuRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLDivElement>(null);
  const user = getCurrentUser();
  const darkMode = mode === "dark";
  const { isPhone, isTablet, isNarrow } = useViewport();
  const compactHeader = isNarrow;

  useEffect(() => {
    setSidebarOpen(shellMode !== "detail" && !isTablet);
  }, [isTablet, shellMode]);

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
    listApplications({
      statuses: [
        "PROCESSING",
        "INTAKE_COMPLETE",
        "FAILED",
        "READY_FOR_REVIEW",
        "REVIEWED",
        "READY_FOR_LICENSING_REVIEW",
        "RETURN_TO_APPLICANT",
        "DEFERRED",
        "DENIED",
      ],
      limit: 300,
    })
      .then(setSearchApps)
      .catch(() => setSearchApps([]));
  }, []);

  useEffect(() => {
    if (!profileOpen && !searchOpen) return;
    const handleClick = (event: MouseEvent) => {
      if (!profileMenuRef.current?.contains(event.target as Node)) {
        setProfileOpen(false);
      }
      if (!searchRef.current?.contains(event.target as Node)) {
        setSearchOpen(false);
      }
    };
    window.addEventListener("mousedown", handleClick);
    return () => window.removeEventListener("mousedown", handleClick);
  }, [profileOpen, searchOpen]);

  const navItems = [
    { id: "dashboard", label: "Dashboard", icon: "\u25ce" },
    { id: "queue", label: "Review queue", icon: "\u25a4", badge: pendingCount },
    { id: "upload", label: "Upload transcript", icon: "\u21a5" },
    { id: "audit", label: "Audit log", icon: "\u2261" },
  ];
  const normalizedSearch = searchQuery.trim().toLowerCase();
  const searchMatches = normalizedSearch
    ? searchApps
        .filter((app) =>
          [
            app.applicationId,
            app.applicantName,
            app.institution,
            app.licenseNumber,
            app.originalFilename,
          ]
            .join(" ")
            .toLowerCase()
            .includes(normalizedSearch)
        )
        .slice(0, 6)
    : [];

  function openSearchTarget(path: string) {
    navigate(path, detailBackStateFor(sourceFromSection(page)));
    setSearchOpen(false);
    setSearchQuery("");
  }

  return (
    <div
      style={{
        width: "100%",
        height: "100vh",
        background: t.bg,
        color: t.ink,
        fontFamily: t.sans,
        display: "grid",
        gridTemplateColumns: sidebarOpen ? "220px 1fr" : "0 1fr",
        gridTemplateRows: "auto 1fr",
        overflow: "hidden",
        transition: "grid-template-columns 180ms ease",
      }}
    >
      {/* Top bar */}
      <div
        style={{
          gridColumn: "1 / -1",
          background: t.primary,
          color: t.primaryInk,
          display: isPhone ? "flex" : "grid",
          flexWrap: isPhone ? "wrap" : undefined,
          gridTemplateColumns: isPhone ? undefined : "minmax(280px, auto) minmax(360px, 1fr) auto",
          alignItems: "center",
          justifyContent: isPhone ? "flex-start" : undefined,
          padding: compactHeader ? "10px 16px" : "10px 22px",
          gap: 12,
          borderBottom: `3px solid ${t.accent}`,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0, flex: isPhone ? "1 1 100%" : "0 1 auto" }}>
          <button
            onClick={() => setSidebarOpen((open) => !open)}
            title={sidebarOpen ? "Hide navigation" : "Show navigation"}
            aria-label={sidebarOpen ? "Hide navigation" : "Show navigation"}
            style={{
              width: 32,
              height: 32,
              border: "1px solid rgba(255,255,255,0.2)",
              background: "rgba(255,255,255,0.08)",
              color: "inherit",
              borderRadius: 4,
              cursor: "pointer",
              fontSize: 18,
              lineHeight: 1,
              fontFamily: t.mono,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              position: "relative",
              overflow: "hidden",
              transition: "background 180ms, border-color 180ms",
            }}
          >
            {[0, 1, 2].map((line) => (
              <span
                key={line}
                style={{
                  position: "absolute",
                  width: 16,
                  height: 2,
                  borderRadius: 2,
                  background: "currentColor",
                  transform: `translateY(${(line - 1) * 5}px) scaleX(${sidebarOpen ? 1 : 0.72})`,
                  transition: "transform 180ms ease",
                }}
              />
            ))}
          </button>
          <button
            onClick={() => navigate(APP_ROUTES.dashboard)}
            title="Home"
            aria-label="Home"
            className="msbn-brand-button"
            style={{
              border: "none",
              background: "transparent",
              color: "inherit",
              padding: 0,
              display: "flex",
              alignItems: "center",
              gap: 12,
              cursor: "pointer",
              fontFamily: "inherit",
              textAlign: "left",
              minWidth: 0,
            }}
          >
          <img
            src="/assets/msbn-logo.png"
            alt="Mississippi Board of Nursing"
            style={{
              width: compactHeader ? 112 : 132,
              height: "auto",
              display: "block",
              background: "#fff",
              borderRadius: 3,
              padding: "3px 5px",
              boxShadow: "0 2px 8px rgba(0,0,0,0.12)",
              flexShrink: 0,
            }}
          />
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
          </button>
        </div>
        <div
          ref={searchRef}
          style={{
            position: "relative",
            flex: isPhone ? "1 1 100%" : undefined,
            width: isPhone ? "100%" : "auto",
            maxWidth: isPhone ? "100%" : "100%",
            minWidth: 0,
            marginLeft: 0,
            order: isPhone ? 3 : 0,
          }}
        >
          <span
            aria-hidden="true"
            style={{
              position: "absolute",
              left: 11,
              top: "50%",
              transform: "translateY(-50%)",
              color: "rgba(255,255,255,0.62)",
              fontSize: 13,
              zIndex: 1,
              pointerEvents: "none",
            }}
          >
            &#8981;
          </span>
          <input
            value={searchQuery}
            onChange={(event) => {
              setSearchQuery(event.target.value);
              setSearchOpen(true);
            }}
            onFocus={() => setSearchOpen(true)}
            onKeyDown={(event) => {
              if (event.key === "Escape") setSearchOpen(false);
              if (event.key === "Enter" && searchMatches[0]) {
                openSearchTarget(
                  isApplicationReviewable(searchMatches[0])
                    ? applicationReviewPath(searchMatches[0])
                    : applicationAuditPath(searchMatches[0])
                );
              }
            }}
            placeholder="Search application ID, name, institution"
            aria-label="Search applications"
            style={{
              width: "100%",
              height: 34,
              border: "1px solid rgba(255,255,255,0.22)",
              background: "rgba(255,255,255,0.1)",
              color: "inherit",
              borderRadius: 4,
              padding: "0 12px 0 32px",
              fontFamily: "inherit",
              fontSize: 12,
              outline: "none",
            }}
          />
          {searchOpen && searchQuery.trim() && (
            <div
              style={{
                position: "absolute",
                top: 40,
                left: 0,
                right: 0,
                background: t.surface,
                color: t.ink,
                border: `1px solid ${t.line}`,
                borderTop: `3px solid ${t.accent}`,
                borderRadius: 4,
                boxShadow: "0 18px 45px rgba(0,0,0,0.28)",
                zIndex: 30,
                overflow: "hidden",
              }}
            >
              {searchMatches.length === 0 && (
                <div style={{ padding: "14px 16px", color: t.ink4, fontSize: 12 }}>
                  No matching applications.
                </div>
              )}
              {searchMatches.map((app) => {
                const reviewable = isApplicationReviewable(app);
                return (
                  <div
                    key={app.applicationId}
                    style={{
                      minHeight: 72,
                      padding: "14px 14px",
                      borderBottom: `1px solid ${t.line2}`,
                      display: "grid",
                      gridTemplateColumns: "minmax(0, 1fr) auto",
                      gap: 10,
                      alignItems: "center",
                    }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: t.ink, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {app.applicantName || app.originalFilename || "Transcript upload"}
                      </div>
                      <div style={{ marginTop: 2, fontSize: 10, color: t.ink4, fontFamily: t.mono, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {app.applicationId} · {app.institution || app.status}
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 6 }}>
                      {reviewable && (
                        <button
                          onClick={() => openSearchTarget(applicationReviewPath(app))}
                          style={{
                            border: `1px solid ${t.accent}`,
                            background: t.accentBg,
                            color: t.accent,
                            borderRadius: 3,
                            padding: "5px 8px",
                            cursor: "pointer",
                            fontFamily: t.mono,
                            fontSize: 10,
                            fontWeight: 800,
                          }}
                        >
                          Review
                        </button>
                      )}
                      <button
                        onClick={() => openSearchTarget(applicationAuditPath(app))}
                        style={{
                          border: `1px solid ${t.line}`,
                          background: t.surfaceAlt,
                          color: t.ink2,
                          borderRadius: 3,
                          padding: "5px 8px",
                          cursor: "pointer",
                          fontFamily: t.mono,
                          fontSize: 10,
                          fontWeight: 800,
                        }}
                      >
                        Audit
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
        <div
          ref={profileMenuRef}
          style={{
            position: "relative",
            marginLeft: 0,
          }}
        >
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
          gridColumn: 1,
          gridRow: 2,
          background: t.surface,
          borderRight: sidebarOpen ? `1px solid ${t.line}` : "none",
          padding: sidebarOpen ? "18px 0" : 0,
          display: "flex",
          flexDirection: "column",
          gap: 2,
          overflow: "hidden",
          opacity: sidebarOpen ? 1 : 0,
          transform: sidebarOpen ? "translateX(0)" : "translateX(-16px)",
          pointerEvents: sidebarOpen ? "auto" : "none",
          transition: "opacity 180ms ease, transform 180ms ease",
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
                cursor: "pointer",
                background: active ? t.accentBg : "transparent",
                color: active ? t.ink : t.ink2,
                fontSize: 13,
                fontWeight: active ? 600 : 500,
                fontFamily: "inherit",
                textAlign: "left",
                borderRadius: 6,
                border: active ? `1px solid ${t.accent}` : "1px solid transparent",
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
      <div style={{ gridColumn: 2, gridRow: 2, overflow: contentOverflow }}>{children}</div>
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
  const { isPhone, isTablet } = useViewport();
  return (
    <div
      style={{
        padding: isPhone ? "20px 16px 16px" : isTablet ? "24px 24px 18px" : "26px 34px 20px",
        borderBottom: `1px solid ${t.line}`,
        background: t.surface,
        display: "flex",
        flexDirection: isTablet ? "column" : "row",
        alignItems: isTablet ? "stretch" : "flex-end",
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
            fontSize: isPhone ? 22 : 26,
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
      {actions && <div style={{ width: isTablet ? "100%" : "auto" }}>{actions}</div>}
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
