import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useT, useThemeMode } from "../theme";
import { getCurrentUser, signOut } from "../auth";
import { useViewport } from "../useViewport";
import { useApplicationList } from "../useApplicationList";
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

type NavItem = {
  id: string;
  label: string;
  section: "main" | "actions";
  icon: (color: string) => React.ReactNode;
  badge?: number;
};

function DashboardIcon({ color }: { color: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <rect x="1.5" y="1.5" width="5.5" height="5.5" rx="1" stroke={color} strokeWidth="1.4" />
      <rect x="9" y="1.5" width="5.5" height="5.5" rx="1" stroke={color} strokeWidth="1.4" />
      <rect x="1.5" y="9" width="5.5" height="5.5" rx="1" stroke={color} strokeWidth="1.4" />
      <rect x="9" y="9" width="5.5" height="5.5" rx="1" stroke={color} strokeWidth="1.4" />
    </svg>
  );
}

function ClipboardIcon({ color }: { color: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <rect x="3" y="3" width="10" height="11.5" rx="1.2" stroke={color} strokeWidth="1.4" />
      <rect x="5.25" y="1.75" width="5.5" height="2.6" rx="0.6" stroke={color} strokeWidth="1.4" fill="none" />
    </svg>
  );
}

function UploadIcon({ color }: { color: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M3.2 11.5a2.7 2.7 0 0 1 .35-5.32 4 4 0 0 1 7.74-.5 2.85 2.85 0 0 1 1.3 5.5"
        stroke={color}
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M8 8.4v5.4M5.7 10.6 8 8.3l2.3 2.3" stroke={color} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function DocumentIcon({ color }: { color: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path d="M3.5 1.75h6L12.5 4.7v9.55H3.5z" stroke={color} strokeWidth="1.4" strokeLinejoin="round" />
      <path d="M5.7 7.6h4.6M5.7 9.9h4.6M5.7 12.2h3" stroke={color} strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function SearchIcon({ color }: { color: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
      <circle cx="7" cy="7" r="4.5" stroke={color} strokeWidth="1.5" />
      <path d="m10.5 10.5 3 3" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function HamburgerIcon({ color }: { color: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <rect x="2" y="3.5"  width="14" height="2" rx="1" fill={color} />
      <rect x="2" y="8"    width="14" height="2" rx="1" fill={color} />
      <rect x="2" y="12.5" width="14" height="2" rx="1" fill={color} />
    </svg>
  );
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
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(shellMode !== "detail");
  const profileMenuRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLDivElement>(null);
  const user = getCurrentUser();
  const darkMode = mode === "dark";
  const { isPhone, isTablet } = useViewport();
  const { apps: searchApps } = useApplicationList({
    statuses: [
      "PROCESSING",
      "INTAKE_COMPLETE",
      "FAILED",
      "READY_FOR_REVIEW",
      "REVIEWED",
      "READY_FOR_LICENSING_REVIEW",
      "DENIED",
    ],
    limit: 300,
    pollMs: 15000,
  });
  const pendingCount = searchApps.filter(
    (a) =>
      a.status === "READY_FOR_REVIEW" &&
      Boolean(a.applicantName.trim() || a.institution.trim())
  ).length;

  useEffect(() => {
    setSidebarOpen(shellMode !== "detail" && !isTablet);
  }, [isTablet, shellMode]);

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

  const navItems: NavItem[] = [
    { id: "dashboard", label: "Dashboard", section: "main", icon: (c) => <DashboardIcon color={c} /> },
    { id: "queue", label: "Review queue", section: "main", icon: (c) => <ClipboardIcon color={c} />, badge: pendingCount },
    { id: "upload", label: "Upload transcript", section: "actions", icon: (c) => <UploadIcon color={c} /> },
    { id: "audit", label: "Audit log", section: "actions", icon: (c) => <DocumentIcon color={c} /> },
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

  const sidebarWidth = sidebarOpen ? 240 : 0;

  const sectionLabelStyle: React.CSSProperties = {
    padding: "0 22px 6px",
    fontSize: 10,
    color: "rgba(255,255,255,0.45)",
    letterSpacing: 1.4,
    textTransform: "uppercase",
    fontFamily: t.mono,
    marginTop: 18,
  };

  const renderNavGroup = (section: "main" | "actions", label: string) => (
    <>
      <div style={sectionLabelStyle}>{label}</div>
      {navItems
        .filter((n) => n.section === section)
        .map((item) => {
          const active = item.id === page;
          const iconColor = active ? "#ffffff" : "rgba(255,255,255,0.6)";
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "10px 14px",
                margin: "2px 12px",
                cursor: "pointer",
                background: active ? t.accent : "transparent",
                color: active ? "#ffffff" : "rgba(255,255,255,0.78)",
                fontSize: 13,
                fontWeight: active ? 600 : 500,
                fontFamily: "inherit",
                textAlign: "left",
                borderRadius: 8,
                border: "1px solid transparent",
                transition: "background 140ms",
              }}
            >
              <span
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: 6,
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  background: active ? "rgba(255,255,255,0.18)" : "rgba(255,255,255,0.05)",
                }}
              >
                {item.icon(iconColor)}
              </span>
              <span style={{ flex: 1 }}>{item.label}</span>
              {item.badge != null && item.badge > 0 && (
                <span
                  style={{
                    background: active ? "rgba(255,255,255,0.22)" : t.accent,
                    color: "#fff",
                    fontSize: 10,
                    fontWeight: 700,
                    padding: "2px 8px",
                    borderRadius: 10,
                    fontFamily: t.mono,
                    letterSpacing: 0.3,
                  }}
                >
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
    </>
  );

  /* left zone width tracks sidebar: wide when open, narrow when closed */
  return (
    <div
      style={{
        width: "100%",
        height: "100vh",
        fontFamily: t.sans,
        display: "grid",
        gridTemplateColumns: `${sidebarWidth}px 1fr`,
        gridTemplateRows: "56px 1fr",
        overflow: "hidden",
        transition: "grid-template-columns 200ms ease",
      }}
    >
      {/* ── Top bar (full width) ── */}
      <div
        style={{
          gridColumn: "1 / -1",
          gridRow: 1,
          background: t.primary,
          color: "#fff",
          display: "flex",
          alignItems: "center",
          position: "relative",
          zIndex: 20,
          borderBottom: `3px solid ${t.accent}`,
          paddingRight: isPhone ? 12 : 20,
        }}
      >
        {/* Hamburger — always leftmost, fixed 56px slot */}
        <button
          onClick={() => setSidebarOpen((o) => !o)}
          title={sidebarOpen ? "Collapse navigation" : "Expand navigation"}
          aria-label={sidebarOpen ? "Collapse navigation" : "Expand navigation"}
          className="msbn-hamburger"
          style={{
            width: 56,
            height: "100%",
            flexShrink: 0,
            border: "none",
            background: "transparent",
            color: "#fff",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <HamburgerIcon color="#fff" />
        </button>

        {/* Logo — always visible, sits right of hamburger */}
        <button
          onClick={() => navigate(APP_ROUTES.dashboard)}
          title="Home"
          aria-label="Home"
          style={{
            border: "none",
            background: "transparent",
            padding: "0 20px 0 0",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            flexShrink: 0,
          }}
        >
          <img
            src="/assets/msbn-logo.png"
            alt="Mississippi Board of Nursing"
            style={{ height: 30, width: "auto", display: "block", objectFit: "contain" }}
          />
        </button>

        {/* Search — position:absolute so it stays truly centered in the bar */}
        <div
          ref={searchRef}
          style={{
            position: "absolute",
            left: "50%",
            transform: "translateX(-50%)",
            width: "min(520px, calc(100% - 340px))",
            zIndex: 21,
          }}
        >
          <span
            aria-hidden="true"
            style={{
              position: "absolute",
              left: 12,
              top: "50%",
              transform: "translateY(-50%)",
              pointerEvents: "none",
              display: "flex",
              opacity: 0.55,
            }}
          >
            <SearchIcon color="#fff" />
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
            placeholder="Search application ID, name, institution…"
            aria-label="Search applications"
            style={{
              width: "100%",
              height: 36,
              border: "1px solid rgba(255,255,255,0.22)",
              background: "rgba(255,255,255,0.1)",
              color: "#fff",
              borderRadius: 8,
              padding: "0 14px 0 36px",
              fontFamily: "inherit",
              fontSize: 13,
              outline: "none",
            }}
          />

          {searchOpen && searchQuery.trim() && (
            <div
              style={{
                position: "absolute",
                top: 44,
                left: 0,
                right: 0,
                background: t.surface,
                color: t.ink,
                border: `1px solid ${t.line}`,
                borderTop: `3px solid ${t.accent}`,
                borderRadius: 8,
                boxShadow: "0 20px 48px rgba(13,34,64,0.22)",
                zIndex: 40,
                overflow: "hidden",
                animation: "popoverIn 0.17s ease",
              }}
            >
              {searchMatches.length === 0 && (
                <div style={{ padding: "14px 16px", color: t.ink4, fontSize: 13 }}>
                  No matching applications.
                </div>
              )}
              {searchMatches.map((app) => {
                const reviewable = isApplicationReviewable(app);
                return (
                  <div
                    key={app.applicationId}
                    style={{
                      minHeight: 68,
                      padding: "12px 14px",
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
                      <div style={{ marginTop: 2, fontSize: 11, color: t.ink4, fontFamily: t.mono, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
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
                            borderRadius: 5,
                            padding: "5px 10px",
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
                          borderRadius: 5,
                          padding: "5px 10px",
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

        {/* Right zone: profile — pushed to far right */}
        <div style={{ marginLeft: "auto", flexShrink: 0 }}>
          <div ref={profileMenuRef} style={{ position: "relative" }}>
            <button
              onClick={() => setProfileOpen((open) => !open)}
              style={{
                border: "1px solid rgba(255,255,255,0.2)",
                background: "rgba(255,255,255,0.1)",
                color: "#fff",
                display: "flex",
                alignItems: "center",
                gap: 9,
                padding: "4px 12px 4px 4px",
                cursor: "pointer",
                fontFamily: "inherit",
                borderRadius: 999,
                transition: "background 140ms",
              }}
            >
              <span
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: 14,
                  background: t.accent,
                  color: "#fff",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: 0.4,
                  flexShrink: 0,
                }}
              >
                {user?.initials ?? "U"}
              </span>
              {!isPhone && (
                <span style={{ fontSize: 13, fontWeight: 500 }}>
                  {user?.displayName ?? "Signed in"}
                </span>
              )}
            </button>

            {profileOpen && (
              <div
                style={{
                  position: "absolute",
                  top: 46,
                  right: 0,
                  width: 270,
                  background: t.surface,
                  color: t.ink,
                  border: `1px solid ${t.line}`,
                  borderTop: `3px solid ${t.accent}`,
                  borderRadius: 8,
                  boxShadow: "0 20px 50px rgba(13,34,64,0.26)",
                  zIndex: 40,
                  padding: 10,
                  animation: "popoverIn 0.17s ease",
                }}
              >
                <div
                  style={{
                    padding: "8px 10px 12px",
                    borderBottom: `1px solid ${t.line2}`,
                    marginBottom: 6,
                  }}
                >
                  <div style={{ fontSize: 13, fontWeight: 700 }}>
                    {user?.displayName ?? "Signed in"}
                  </div>
                  <div style={{ fontSize: 11, color: t.ink4, marginTop: 3 }}>
                    {user?.email ?? "Reviewer account"}
                  </div>
                </div>

                <button
                  onClick={() => { setProfileOpen(false); onNavigate("settings"); }}
                  style={{
                    width: "100%",
                    border: "none",
                    background: "transparent",
                    color: t.ink2,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "9px 10px",
                    borderRadius: 5,
                    cursor: "pointer",
                    fontFamily: "inherit",
                    fontSize: 13,
                    textAlign: "left",
                  }}
                >
                  <span>Settings</span>
                  <span style={{ color: t.ink4, fontFamily: t.mono, fontSize: 11 }}>&rarr;</span>
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
      </div>

      {/* ── Sidebar ── */}
      <aside
        style={{
          gridColumn: 1,
          gridRow: 2,
          background: t.primary,
          color: "#fff",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          opacity: sidebarOpen ? 1 : 0,
          pointerEvents: sidebarOpen ? "auto" : "none",
          transition: "opacity 200ms ease",
          borderRight: "1px solid rgba(255,255,255,0.07)",
        }}
      >
        {/* Nav */}
        <nav style={{ display: "flex", flexDirection: "column", flex: 1, overflowY: "auto" }}>
          {renderNavGroup("main", "Main")}
          {renderNavGroup("actions", "Actions")}
        </nav>

      </aside>

      {/* ── Page content ── */}
      <div
        style={{
          gridColumn: 2,
          gridRow: 2,
          overflow: contentOverflow,
          minHeight: 0,
          background: t.bg,
          color: t.ink,
        }}
      >
        {children}
      </div>
    </div>
  );
}

// ─── Reusable sub-components ────────────────────────────────────────────────

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  const t = useT();
  const { isPhone, isTablet } = useViewport();
  return (
    <div
      style={{
        padding: isPhone ? "20px 16px 18px" : isTablet ? "26px 24px 22px" : "30px 34px 24px",
        background: t.bg,
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
              letterSpacing: 1.4,
              textTransform: "uppercase",
              marginBottom: 10,
              fontFamily: t.mono,
              fontWeight: 600,
            }}
          >
            {eyebrow}
          </div>
        )}
        <div
          style={{
            fontSize: isPhone ? 26 : 34,
            fontWeight: 700,
            fontFamily: t.serif,
            letterSpacing: -0.5,
            color: t.ink,
            lineHeight: 1.1,
          }}
        >
          {title}
        </div>
        {subtitle && (
          <div style={{ fontSize: 14, color: t.ink3, marginTop: 6 }}>
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
        borderRadius: 10,
        overflow: "hidden",
      }}
    >
      {(title || actions) && (
        <div
          style={{
            padding: "16px 20px",
            borderBottom: `1px solid ${t.line2}`,
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 16, fontWeight: 700, fontFamily: t.serif, color: t.ink }}>
              {title}
            </div>
            {subtitle && (
              <div style={{ fontSize: 12, color: t.ink4, marginTop: 3 }}>
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
    accent:  { bg: t.accent,  fg: t.primaryInk, border: t.accent },
    ghost:   { bg: "transparent", fg: t.ink2, border: t.line },
    outline: { bg: t.surface, fg: t.primary,    border: t.primary },
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
        borderRadius: 6,
        cursor: disabled ? "not-allowed" : "pointer",
        letterSpacing: 0.1,
      }}
    >
      {children}
    </button>
  );
}
