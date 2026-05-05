import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useT } from "../theme";
import { PageHeader, Card } from "../components/Shell";
import {
  applicationDetailPath,
  detailBackStateFor,
  isApplicationReviewable,
} from "../navigation";
import { deleteApplication } from "../api";
import type { Application } from "../types";
import { useApplicationList } from "../useApplicationList";

function timeAgo(hrs: number) {
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function FlagDot({ n, color }: { n: number; color: string }) {
  const t = useT();
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        minWidth: 20,
        height: 18,
        padding: "0 5px",
        background: color,
        color: "#fff",
        fontSize: 10,
        fontWeight: 700,
        fontFamily: t.mono,
        borderRadius: 2,
        letterSpacing: 0.2,
      }}
    >
      {n}
    </span>
  );
}

function isReadyForReview(app: Application) {
  return isApplicationReviewable(app);
}

function isProcessing(app: Application) {
  return app.status === "PROCESSING" || app.status === "INTAKE_COMPLETE";
}

function displayApplicant(app: Application) {
  return app.applicantName || app.originalFilename || "Transcript upload";
}

function displayInstitution(app: Application) {
  if (app.institution) return app.institution;
  if (isProcessing(app)) return "Extraction in progress";
  if (app.status === "FAILED") return "Processing failed";
  return "Pending metadata";
}

function transcriptActivityState(app: Application) {
  if (app.status === "INTAKE_COMPLETE") {
    return { label: "queued", colorKey: "low" as const };
  }
  if (app.status === "PROCESSING") {
    return { label: "processing", colorKey: "med" as const };
  }
  if (app.status === "FAILED") {
    return { label: "failed", colorKey: "high" as const };
  }
  return { label: "processed", colorKey: "ok" as const };
}

function StatusPill({ status }: { status: string }) {
  const t = useT();
  const queued = status === "INTAKE_COMPLETE";
  const processing = status === "PROCESSING";
  const failed = status === "FAILED";
  const reviewed = status === "REVIEWED";
  const label = queued
    ? "Queued"
    : processing
    ? "Processing"
    : status === "READY_FOR_REVIEW"
      ? "Processed"
      : reviewed
        ? "Processed"
        : status.replaceAll("_", " ").toLowerCase();
  const borderColor = failed ? t.high : processing ? t.med : queued ? t.low : t.ok;
  const bgColor = failed ? t.highBg : processing ? t.medBg : queued ? t.lowBg : t.okBg;
  const textColor = failed ? t.high : processing ? t.med : queued ? t.low : t.ok;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        border: `1.5px solid ${borderColor}`,
        background: bgColor,
        color: textColor,
        borderRadius: 999,
        padding: "4px 14px",
        fontSize: 11,
        fontWeight: 700,
        fontFamily: t.mono,
        letterSpacing: 0.4,
        textTransform: "uppercase",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );
}

function ClipboardStatIcon({ color }: { color: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <rect x="3.5" y="3.5" width="11" height="13" rx="1.4" stroke={color} strokeWidth="1.6" />
      <rect x="6" y="2" width="6" height="3" rx="0.7" stroke={color} strokeWidth="1.6" fill="none" />
      <path d="M6.4 9h5.2M6.4 11.6h3.5" stroke={color} strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function GearIcon({ color }: { color: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <circle cx="9" cy="9" r="2.4" stroke={color} strokeWidth="1.5" />
      <path
        d="M9 1.6v2M9 14.4v2M3.8 3.8l1.4 1.4M12.8 12.8l1.4 1.4M1.6 9h2M14.4 9h2M3.8 14.2l1.4-1.4M12.8 5.2l1.4-1.4"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function FlagStatIcon({ color }: { color: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <path d="M4.5 2.5v13" stroke={color} strokeWidth="1.6" strokeLinecap="round" />
      <path
        d="M4.5 3h8.6l-1.7 3.1 1.7 3.1H4.5"
        stroke={color}
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CheckIcon({ color }: { color: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <path
        d="M3.5 9.5 7 13l7.5-8"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function UploadIconLg({ color }: { color: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M3.2 11.5a2.7 2.7 0 0 1 .35-5.32 4 4 0 0 1 7.74-.5 2.85 2.85 0 0 1 1.3 5.5"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M8 8.4v5.4M5.7 10.6 8 8.3l2.3 2.3" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

type SortKey = "application" | "applicant" | "institution" | "status" | "submitted" | "flags";
type SortDirection = "asc" | "desc";

interface EnabledGroups {
  processing: boolean;
  failed: boolean;
  ready: boolean;
  reviewed: boolean;
}

const ACTIVE_STATUSES = new Set(["PROCESSING", "INTAKE_COMPLETE", "FAILED", "READY_FOR_REVIEW"]);

const REVIEW_OUTCOME_STATUSES = [
  "REVIEWED",
  "READY_FOR_LICENSING_REVIEW",
  "DENIED",
];

// Always fetch active statuses so stats cards are never affected by filters.
// The reviewed group includes terminal/review-outcome statuses, not only REVIEWED.
function resolveStatuses(groups: EnabledGroups): string[] {
  return [
    "PROCESSING",
    "INTAKE_COMPLETE",
    "FAILED",
    "READY_FOR_REVIEW",
    ...(groups.reviewed ? REVIEW_OUTCOME_STATUSES : []),
  ];
}

export function DashboardPage({
  onNavigate,
}: {
  onNavigate: (id: string) => void;
}) {
  const t = useT();
  const navigate = useNavigate();
  const navigateFromDashboard = (path: string) => {
    navigate(path, detailBackStateFor("dashboard"));
  };
  const [apps, setApps] = useState<Application[]>([]);
  const [actionError, setActionError] = useState<string | null>(null);

  const [enabledGroups, setEnabledGroups] = useState<EnabledGroups>({
    processing: true,
    failed: true,
    ready: true,
    reviewed: false,
  });
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("submitted");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [pageSize, setPageSize] = useState(10);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const activeStatuses = resolveStatuses(enabledGroups);
  const { apps: loadedApps, error } = useApplicationList({
    statuses: activeStatuses,
    limit: 200,
    pollMs: 3000,
  });
  const currentError = actionError ?? error;

  useEffect(() => {
    setApps(loadedApps);
  }, [loadedApps]);

  // Client-side pipeline: status filter → date filter → sort → paginate.
  const activeStatusSet = new Set<string>([
    ...(enabledGroups.processing ? ["PROCESSING", "INTAKE_COMPLETE"] : []),
    ...(enabledGroups.failed ? ["FAILED"] : []),
    ...(enabledGroups.ready ? ["READY_FOR_REVIEW"] : []),
    ...(enabledGroups.reviewed ? REVIEW_OUTCOME_STATUSES : []),
  ]);
  let displayed = apps.filter((a) =>
    activeStatusSet.has(a.status) ||
    (enabledGroups.reviewed && !ACTIVE_STATUSES.has(a.status))
  );
  if (dateFrom) {
    displayed = displayed.filter((a) => a.submittedAt >= dateFrom);
  }
  if (dateTo) {
    displayed = displayed.filter(
      (a) => a.submittedAt <= `${dateTo}T23:59:59`
    );
  }
  displayed.sort((a, b) => {
    let value = 0;
    if (sortBy === "application") value = a.applicationId.localeCompare(b.applicationId);
    if (sortBy === "applicant") value = displayApplicant(a).localeCompare(displayApplicant(b));
    if (sortBy === "institution") value = displayInstitution(a).localeCompare(displayInstitution(b));
    if (sortBy === "status") value = a.status.localeCompare(b.status);
    if (sortBy === "submitted") value = a.submittedAt.localeCompare(b.submittedAt);
    if (sortBy === "flags") value = a.flagCount - b.flagCount;
    return sortDirection === "asc" ? value : -value;
  });
  const queue = displayed.slice(0, pageSize);

  // Stats are always computed from the unfiltered fetch.
  const awaiting = apps.filter(isReadyForReview);
  const processing = apps.filter(isProcessing);
  const failed = apps.filter((a) => a.status === "FAILED");
  const highSeverity = awaiting.filter((a) => a.highestSeverity === "High").length;
  const flagged = awaiting.reduce((sum, app) => sum + app.flagCount, 0);

  const today = new Date();
  const eyebrowDate = today.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
  const eyebrowTime = today.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  const stats: {
    label: string;
    value: string;
    delta: string;
    accent: string;
    bg: string;
    icon: (color: string) => React.ReactNode;
  }[] = [
    {
      label: "Awaiting review",
      value: String(awaiting.length),
      delta: currentError ?? "From live API",
      accent: t.accent,
      bg: t.accentBg,
      icon: (c) => <ClipboardStatIcon color={c} />,
    },
    {
      label: "Processing",
      value: String(processing.length),
      delta: failed.length ? `${failed.length} failed` : "Visible after S3 upload",
      accent: t.med,
      bg: t.medBg,
      icon: (c) => <GearIcon color={c} />,
    },
    {
      label: "High-severity flags",
      value: String(highSeverity),
      delta: `Across ${awaiting.length} apps`,
      accent: t.high,
      bg: t.highBg,
      icon: (c) => <FlagStatIcon color={c} />,
    },
    {
      label: "Total open flags",
      value: String(flagged),
      delta: "Ready for reviewer action",
      accent: t.ok,
      bg: t.okBg,
      icon: (c) => <CheckIcon color={c} />,
    },
  ];

  function toggleGroup(key: keyof EnabledGroups) {
    setEnabledGroups((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  function toggleSort(key: SortKey) {
    if (sortBy === key) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortBy(key);
    setSortDirection(key === "submitted" || key === "flags" ? "desc" : "asc");
  }

  async function handleDelete() {
    if (selected.size === 0) return;
    const ids = Array.from(selected);
    const noun = ids.length === 1 ? "1 entry" : `${ids.length} entries`;
    if (!window.confirm(`Permanently delete ${noun}? This removes all records and files and cannot be undone.`)) return;
    setDeleting(true);
    setActionError(null);
    try {
      const results = await Promise.allSettled(ids.map((appId) => deleteApplication(appId)));
      const failedIds = results.flatMap((result, index) =>
        result.status === "rejected" ? [ids[index]] : []
      );

      setApps((prev) => prev.filter((a) => !ids.includes(a.applicationId) || failedIds.includes(a.applicationId)));
      setSelected(new Set());

      if (failedIds.length > 0) {
        setActionError(
          failedIds.length === 1
            ? `Delete failed for ${failedIds[0]}`
            : `Delete failed for ${failedIds.length} selected applications`
        );
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Delete failed";
      setActionError(msg);
    } finally {
      setDeleting(false);
    }
  }

  const statusToggles: { key: keyof EnabledGroups; label: string; color: string }[] = [
    { key: "processing", label: "Processing", color: t.med },
    { key: "failed",     label: "Failed",     color: t.high },
    { key: "ready",      label: "Ready",      color: t.ok },
    { key: "reviewed",   label: "Reviewed",   color: t.ink3 },
  ];

  const allActive = (Object.values(enabledGroups).filter(Boolean).length === 4);
  function selectAll() {
    setEnabledGroups({ processing: true, failed: true, ready: true, reviewed: true });
  }

  // Shared select style.
  const selectStyle: React.CSSProperties = {
    fontSize: 11,
    fontFamily: t.mono,
    color: t.ink2,
    background: t.surface,
    border: `1px solid ${t.line}`,
    borderRadius: 3,
    padding: "4px 8px",
    cursor: "pointer",
    outline: "none",
  };

  return (
    <>
      <PageHeader
        eyebrow={`${eyebrowDate} — ${eyebrowTime} CT`}
        title="Reviewer dashboard"
        subtitle={
          <span>
            {awaiting.length} applications awaiting review &middot;{" "}
            <span style={{ color: t.high, fontWeight: 600 }}>
              {highSeverity} high severity
            </span>
          </span>
        }
        actions={
          <button
            onClick={() => onNavigate("upload")}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              background: t.primary,
              color: "#fff",
              border: `1px solid ${t.primary}`,
              borderRadius: 8,
              padding: "10px 16px",
              fontSize: 13,
              fontWeight: 600,
              fontFamily: "inherit",
              cursor: "pointer",
              letterSpacing: 0.1,
            }}
          >
            <UploadIconLg color="#fff" />
            Upload transcript
          </button>
        }
      />

      <div
        style={{
          padding: "22px 34px 40px",
          display: "flex",
          flexDirection: "column",
          gap: 18,
        }}
      >
        {currentError && (
          <div
            style={{
              background: t.highBg,
              border: `1px solid ${t.high}`,
              borderRadius: 4,
              padding: "12px 14px",
              color: t.high,
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            {currentError}
          </div>
        )}
        {/* Stats row */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: 14,
          }}
        >
          {stats.map((s) => (
            <div
              key={s.label}
              style={{
                background: s.bg,
                border: `1px solid ${s.bg}`,
                borderLeft: `5px solid ${s.accent}`,
                padding: "20px 22px",
                borderRadius: 10,
                position: "relative",
                minHeight: 150,
                display: "flex",
                flexDirection: "column",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  justifyContent: "space-between",
                  gap: 10,
                }}
              >
                <div
                  style={{
                    fontSize: 11,
                    color: s.accent,
                    letterSpacing: 0.7,
                    textTransform: "uppercase",
                    fontWeight: 700,
                    lineHeight: 1.3,
                    maxWidth: 140,
                  }}
                >
                  {s.label}
                </div>
                <span
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: 8,
                    background: "rgba(255,255,255,0.65)",
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                  }}
                >
                  {s.icon(s.accent)}
                </span>
              </div>
              <div
                style={{
                  fontSize: 48,
                  fontWeight: 700,
                  fontFamily: t.serif,
                  color: s.accent,
                  marginTop: 14,
                  letterSpacing: -1,
                  lineHeight: 1,
                }}
              >
                {s.value}
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: s.accent,
                  opacity: 0.78,
                  marginTop: 10,
                  fontWeight: 500,
                }}
              >
                {s.delta}
              </div>
            </div>
          ))}
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "2.2fr 0.65fr",
            gap: 18,
          }}
        >
          <Card
            title="Transcript activity"
            subtitle={`${queue.length} of ${displayed.length} entries`}
            pad={0}
            actions={
              <button
                onClick={() => onNavigate("queue")}
                style={{
                  border: "none",
                  background: "transparent",
                  color: t.accent,
                  fontSize: 13,
                  fontWeight: 600,
                  fontFamily: "inherit",
                  cursor: "pointer",
                  padding: "4px 6px",
                }}
              >
                View all &rarr;
              </button>
            }
          >
            {/* Filter toolbar */}
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: 10,
                padding: "10px 14px",
                borderBottom: `1px solid ${t.line}`,
                background: t.surfaceAlt,
              }}
            >
              {/* Status toggles */}
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <button
                  onClick={selectAll}
                  style={{
                    fontSize: 12,
                    fontFamily: "inherit",
                    fontWeight: 600,
                    padding: "6px 16px",
                    borderRadius: 999,
                    cursor: "pointer",
                    border: `1.5px solid ${allActive ? t.accent : t.line}`,
                    background: "transparent",
                    color: allActive ? t.accent : t.ink3,
                    transition: "border-color 0.15s, color 0.15s",
                  }}
                >
                  All
                </button>
                {statusToggles.map(({ key, label, color }) => {
                  const active = enabledGroups[key];
                  return (
                    <button
                      key={key}
                      onClick={() => toggleGroup(key)}
                      style={{
                        fontSize: 12,
                        fontFamily: "inherit",
                        fontWeight: 600,
                        padding: "6px 16px",
                        borderRadius: 999,
                        cursor: "pointer",
                        border: `1.5px solid ${active ? color : t.line}`,
                        background: "transparent",
                        color: active ? color : t.ink3,
                        transition: "border-color 0.15s, color 0.15s",
                      }}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>

              {/* Divider */}
              <div
                style={{
                  width: 1,
                  height: 20,
                  background: t.line,
                  margin: "0 2px",
                }}
              />

              {/* Date range */}
              <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span
                  style={{
                    fontSize: 10,
                    fontFamily: t.mono,
                    color: t.ink4,
                    textTransform: "uppercase",
                    letterSpacing: 0.3,
                  }}
                >
                  From
                </span>
                <input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  style={{ ...selectStyle, padding: "3px 6px" }}
                />
                <span
                  style={{
                    fontSize: 10,
                    fontFamily: t.mono,
                    color: t.ink4,
                    textTransform: "uppercase",
                    letterSpacing: 0.3,
                  }}
                >
                  To
                </span>
                <input
                  type="date"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  style={{ ...selectStyle, padding: "3px 6px" }}
                />
                {(dateFrom || dateTo) && (
                  <button
                    onClick={() => { setDateFrom(""); setDateTo(""); }}
                    style={{
                      fontSize: 10,
                      fontFamily: t.mono,
                      color: t.ink4,
                      background: "transparent",
                      border: "none",
                      cursor: "pointer",
                      padding: "2px 4px",
                    }}
                    title="Clear date filter"
                  >
                    ✕
                  </button>
                )}
              </div>

              {/* Divider */}
              <div
                style={{
                  width: 1,
                  height: 20,
                  background: t.line,
                  margin: "0 2px",
                }}
              />

              {/* Sort */}
              <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span
                  style={{
                    fontSize: 10,
                    fontFamily: t.mono,
                    color: t.ink4,
                    textTransform: "uppercase",
                    letterSpacing: 0.3,
                  }}
                >
                  Sort
                </span>
                <select
                  value={`${sortBy}:${sortDirection}`}
                  onChange={(e) => {
                    const [key, direction] = e.target.value.split(":") as [SortKey, SortDirection];
                    setSortBy(key);
                    setSortDirection(direction);
                  }}
                  style={selectStyle}
                >
                  <option value="submitted:desc">Newest first</option>
                  <option value="submitted:asc">Oldest first</option>
                  <option value="status:asc">Status A-Z</option>
                  <option value="institution:asc">Institution A-Z</option>
                  <option value="flags:desc">Most flags</option>
                </select>
              </div>

              {/* Per page */}
              <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span
                  style={{
                    fontSize: 10,
                    fontFamily: t.mono,
                    color: t.ink4,
                    textTransform: "uppercase",
                    letterSpacing: 0.3,
                  }}
                >
                  Show
                </span>
                <select
                  value={pageSize}
                  onChange={(e) => setPageSize(Number(e.target.value))}
                  style={selectStyle}
                >
                  <option value={10}>10</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                </select>
              </div>

              {/* Delete selected — only visible when rows are checked */}
              {selected.size > 0 && (
                <>
                  <div style={{ width: 1, height: 20, background: t.line, margin: "0 2px" }} />
                  <button
                    onClick={handleDelete}
                    disabled={deleting}
                    style={{
                      fontSize: 11,
                      fontFamily: t.mono,
                      fontWeight: 700,
                      letterSpacing: 0.3,
                      textTransform: "uppercase",
                      padding: "4px 12px",
                      borderRadius: 2,
                      cursor: deleting ? "default" : "pointer",
                      border: `1px solid ${t.high}`,
                      background: t.high,
                      color: "#fff",
                      opacity: deleting ? 0.6 : 1,
                    }}
                  >
                    {deleting ? "Deleting…" : `Delete ${selected.size} selected`}
                  </button>
                </>
              )}
            </div>

            {/* Table */}
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: 13,
              }}
            >
              <thead>
                <tr style={{ background: t.surfaceAlt }}>
                  {/* Select-all checkbox */}
                  <th
                    style={{
                      padding: "9px 10px 9px 14px",
                      borderBottom: `1px solid ${t.line}`,
                      width: 32,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={queue.length > 0 && queue.every((r) => selected.has(r.applicationId))}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelected(new Set(queue.map((r) => r.applicationId)));
                        } else {
                          setSelected(new Set());
                        }
                      }}
                      style={{ cursor: "pointer" }}
                    />
                  </th>
                  {([
                    ["application", "Application"],
                    ["applicant", "Applicant"],
                    ["institution", "Institution"],
                    ["status", "Status"],
                    ["submitted", "Age"],
                    ["flags", "Flags"],
                    [null, ""],
                  ] as const).map(([key, label], i) => (
                    <th
                      key={i}
                      style={{
                        textAlign: "left",
                        padding: "7px 14px",
                        fontSize: 10,
                        letterSpacing: 0.5,
                        textTransform: "uppercase",
                        fontWeight: 600,
                        color: t.ink3,
                        fontFamily: t.mono,
                        borderBottom: `1px solid ${t.line}`,
                      }}
                    >
                      {key ? (
                        <button
                          onClick={() => toggleSort(key)}
                          style={{
                            border: "none",
                            background: "transparent",
                            color: sortBy === key ? t.primary : t.ink3,
                            padding: "2px 0",
                            cursor: "pointer",
                            font: "inherit",
                            textTransform: "inherit",
                            letterSpacing: "inherit",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 5,
                          }}
                        >
                          {label}
                          <span style={{ color: sortBy === key ? t.accent : t.ink4 }}>
                            {sortBy === key ? (sortDirection === "asc" ? "\u2191" : "\u2193") : "\u2195"}
                          </span>
                        </button>
                      ) : label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {queue.length === 0 && (
                  <tr>
                    <td
                      colSpan={8}
                      style={{
                        padding: "34px 18px",
                        textAlign: "center",
                        color: t.ink4,
                        fontSize: 13,
                      }}
                    >
                      No transcript activity matches the current filters.
                    </td>
                  </tr>
                )}
                {queue.map((r, i) => {
                  const target = applicationDetailPath(r, "dashboard");
                  return (
                    <ActivityRow
                      key={r.applicationId}
                      app={r}
                      target={target}
                      isLast={i === queue.length - 1}
                      isSelected={selected.has(r.applicationId)}
                      onSelect={(id, checked) => {
                        setSelected((prev) => {
                          const next = new Set(prev);
                          if (checked) next.add(id);
                          else next.delete(id);
                          return next;
                        });
                      }}
                      onNavigate={navigateFromDashboard}
                    />
                  );
                })}
              </tbody>
            </table>
          </Card>

          {/* Recent activity */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 18,
            }}
          >
            <Card title="Recent activity" subtitle="Last 48 hours" pad={0}>
              <div>
                {queue.length === 0 && (
                  <div
                    style={{
                      padding: "34px 18px",
                      textAlign: "center",
                      color: t.ink4,
                      fontSize: 13,
                    }}
                  >
                    No recent activity.
                  </div>
                )}
                {queue.map((a, i) => {
                  const target = applicationDetailPath(a, "dashboard");
                  const activity = transcriptActivityState(a);
                  return (
                    <div
                      key={a.applicationId}
                      onClick={() => target && navigateFromDashboard(target)}
                      onKeyDown={(e) => {
                        if (!target) return;
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          navigateFromDashboard(target);
                        }
                      }}
                      tabIndex={target ? 0 : undefined}
                      aria-label={
                        target ? `Open ${displayApplicant(a)}` : undefined
                      }
                      style={{
                        padding: "14px 18px",
                        borderBottom:
                          i < queue.length - 1
                            ? `1px solid ${t.line2}`
                            : "none",
                        display: "flex",
                        gap: 12,
                        alignItems: "flex-start",
                        cursor: target ? "pointer" : "default",
                      }}
                    >
                      <div
                        style={{
                          width: 32,
                          height: 32,
                          borderRadius: 16,
                          background: t.surfaceAlt,
                          color: t.ink3,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: 11,
                          fontWeight: 700,
                          fontFamily: t.mono,
                          letterSpacing: 0.4,
                          flexShrink: 0,
                        }}
                      >
                        SY
                      </div>
                      <div
                        style={{
                          flex: 1,
                          fontSize: 13,
                          color: t.ink2,
                          lineHeight: 1.45,
                          minWidth: 0,
                        }}
                      >
                        <div>
                          <span style={{ fontWeight: 700, color: t.ink }}>
                            System
                          </span>{" "}
                          <span style={{ color: t.ink3 }}>{activity.label}</span>{" "}
                          <span
                            style={{
                              fontFamily: t.mono,
                              fontSize: 12,
                              color: t.accent,
                              fontWeight: 600,
                            }}
                          >
                            {a.applicationId}
                          </span>
                        </div>
                        <div
                          style={{
                            fontSize: 11,
                            color: t.ink4,
                            marginTop: 3,
                          }}
                        >
                          {timeAgo(a.ageHours)}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}

// Extracted to its own component so hover state is per-row, not shared.
function ActivityRow({
  app: r,
  target,
  isLast,
  isSelected,
  onSelect,
  onNavigate,
}: {
  app: Application;
  target: string | null;
  isLast: boolean;
  isSelected: boolean;
  onSelect: (id: string, checked: boolean) => void;
  onNavigate: (path: string) => void;
}) {
  const t = useT();
  const [hovered, setHovered] = useState(false);

  return (
    <tr
      onClick={() => target && onNavigate(target)}
      onKeyDown={(e) => {
        if (!target) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onNavigate(target);
        }
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      tabIndex={target ? 0 : undefined}
      aria-label={target ? `Open ${displayApplicant(r)}` : undefined}
      style={{
        borderBottom: isLast ? "none" : `1px solid ${t.line2}`,
        cursor: target ? "pointer" : "default",
        background: isSelected ? t.accentBg : hovered && target ? t.surfaceAlt : "transparent",
        transition: "background 0.1s",
      }}
    >
      {/* Row checkbox */}
      <td
        style={{ padding: "11px 10px 11px 14px", width: 32 }}
        onClick={(e) => e.stopPropagation()}
      >
        <input
          type="checkbox"
          checked={isSelected}
          onChange={(e) => onSelect(r.applicationId, e.target.checked)}
          style={{ cursor: "pointer" }}
        />
      </td>
      <td
        style={{
          padding: "11px 14px",
          fontFamily: t.mono,
          fontSize: 11,
          color: t.ink2,
        }}
      >
        {r.applicationId}
      </td>
      <td
        style={{
          padding: "11px 14px",
          fontWeight: 500,
          color: t.ink,
        }}
      >
        {displayApplicant(r)}
      </td>
      <td
        style={{
          padding: "11px 14px",
          color: t.ink3,
          fontSize: 12,
        }}
      >
        {displayInstitution(r)}
      </td>
      <td style={{ padding: "11px 14px" }}>
        <StatusPill status={r.status} />
      </td>
      <td
        style={{
          padding: "11px 14px",
          color: t.ink3,
          fontFamily: t.mono,
          fontSize: 11,
        }}
      >
        {timeAgo(r.ageHours)}
      </td>
      <td style={{ padding: "11px 14px" }}>
        <div style={{ display: "flex", gap: 4 }}>
          {r.flagCount > 0 && (
            <FlagDot
              n={r.flagCount}
              color={r.highestSeverity === "High" ? t.high : t.med}
            />
          )}
          {r.flagCount === 0 && (
            <span
              style={{
                fontSize: 10,
                color: t.ok,
                fontFamily: t.mono,
                letterSpacing: 0.4,
                textTransform: "uppercase",
              }}
            >
              &check; clean
            </span>
          )}
        </div>
      </td>
      <td style={{ padding: "11px 14px", textAlign: "right" }}>
        <button
          onClick={(e) => {
            e.stopPropagation();
            if (target) onNavigate(target);
          }}
          disabled={!target}
          style={{
            border: "none",
            background: "transparent",
            padding: 0,
            color: target ? t.primary : t.ink4,
            fontSize: 12,
            fontWeight: 600,
            cursor: target ? "pointer" : "default",
            fontFamily: "inherit",
          }}
        >
          {isReadyForReview(r)
            ? "Review →"
            : r.status === "FAILED"
              ? "Audit →"
              : target
                ? "Open →"
                : "Waiting"}
        </button>
      </td>
    </tr>
  );
}
