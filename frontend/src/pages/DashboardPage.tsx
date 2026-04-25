import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useT } from "../theme";
import { PageHeader, Card, Btn } from "../components/Shell";
import { listApplications, deleteApplication } from "../api";
import type { Application } from "../types";

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

function hasExtractedSummary(app: Application) {
  return Boolean(app.applicantName.trim() || app.institution.trim());
}

function isReadyForReview(app: Application) {
  return app.status === "READY_FOR_REVIEW" && hasExtractedSummary(app);
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

function StatusPill({ status }: { status: string }) {
  const t = useT();
  const processing = status === "PROCESSING" || status === "INTAKE_COMPLETE";
  const failed = status === "FAILED";
  const reviewed = status === "REVIEWED";
  const label = processing
    ? "Processing"
    : status === "READY_FOR_REVIEW"
      ? "Ready"
      : reviewed
        ? "Reviewed"
        : status.replaceAll("_", " ").toLowerCase();
  const borderColor = failed ? t.high : processing ? t.med : reviewed ? t.ink3 : t.ok;
  const bgColor = failed ? t.highBg : processing ? t.medBg : reviewed ? t.surfaceAlt : t.okBg;
  const textColor = failed ? t.high : processing ? t.med : reviewed ? t.ink3 : t.ok;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        border: `1px solid ${borderColor}`,
        background: bgColor,
        color: textColor,
        borderRadius: 2,
        padding: "2px 7px",
        fontSize: 10,
        fontWeight: 700,
        fontFamily: t.mono,
        letterSpacing: 0.3,
        textTransform: "uppercase",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );
}

function applicationTarget(app: Application) {
  if (isReadyForReview(app)) return `/review/${app.applicationId}`;
  if (app.status === "FAILED") return `/audit/${app.applicationId}`;
  if (app.status === "REVIEWED") return `/audit/${app.applicationId}`;
  return null;
}

type SortKey = "date_desc" | "date_asc" | "status";

interface EnabledGroups {
  processing: boolean;
  failed: boolean;
  ready: boolean;
  reviewed: boolean;
}

// Always fetch the four default statuses so stats cards are never affected by
// the filter toggles. REVIEWED is only added when that toggle is on.
function resolveStatuses(groups: EnabledGroups): string[] {
  return [
    "PROCESSING",
    "INTAKE_COMPLETE",
    "FAILED",
    "READY_FOR_REVIEW",
    ...(groups.reviewed ? ["REVIEWED"] : []),
  ];
}

export function DashboardPage({
  onNavigate,
}: {
  onNavigate: (id: string) => void;
}) {
  const t = useT();
  const navigate = useNavigate();
  const [apps, setApps] = useState<Application[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [enabledGroups, setEnabledGroups] = useState<EnabledGroups>({
    processing: true,
    failed: true,
    ready: true,
    reviewed: false,
  });
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("date_desc");
  const [pageSize, setPageSize] = useState(10);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);

  // Keep a stable ref to enabledGroups for the polling interval.
  const groupsRef = useRef(enabledGroups);
  groupsRef.current = enabledGroups;

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      const statuses = resolveStatuses(groupsRef.current);
      listApplications({ statuses, limit: 200 })
        .then((items) => {
          if (cancelled) return;
          setApps(items);
          setError(null);
        })
        .catch((err: Error) => {
          if (!cancelled) setError(err.message);
        });
    };
    load();
    const interval = window.setInterval(load, 8000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  // Re-mount the effect (and refetch immediately) when the status filter changes.
  }, [enabledGroups]);

  // Client-side pipeline: status filter → date filter → sort → paginate.
  const activeStatuses = new Set<string>([
    ...(enabledGroups.processing ? ["PROCESSING", "INTAKE_COMPLETE"] : []),
    ...(enabledGroups.failed ? ["FAILED"] : []),
    ...(enabledGroups.ready ? ["READY_FOR_REVIEW"] : []),
    ...(enabledGroups.reviewed ? ["REVIEWED"] : []),
  ]);
  let displayed = apps.filter((a) => activeStatuses.has(a.status));
  if (dateFrom) {
    displayed = displayed.filter((a) => a.submittedAt >= dateFrom);
  }
  if (dateTo) {
    displayed = displayed.filter(
      (a) => a.submittedAt <= `${dateTo}T23:59:59`
    );
  }
  if (sortBy === "date_desc") {
    displayed.sort((a, b) => b.submittedAt.localeCompare(a.submittedAt));
  } else if (sortBy === "date_asc") {
    displayed.sort((a, b) => a.submittedAt.localeCompare(b.submittedAt));
  } else {
    displayed.sort((a, b) => a.status.localeCompare(b.status));
  }
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

  const stats = [
    {
      label: "Awaiting review",
      value: String(awaiting.length),
      delta: error ?? "from live API",
      accent: t.accent,
    },
    {
      label: "Processing",
      value: String(processing.length),
      delta: failed.length ? `${failed.length} failed` : "visible after S3 upload",
      accent: processing.length ? t.med : t.ink2,
    },
    {
      label: "High-severity flags",
      value: String(highSeverity),
      delta: `across ${awaiting.length} apps`,
      accent: t.high,
    },
    {
      label: "Total open flags",
      value: String(flagged),
      delta: "ready for reviewer action",
      accent: t.ok,
    },
  ];

  function toggleGroup(key: keyof EnabledGroups) {
    setEnabledGroups((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  async function handleDelete() {
    if (selected.size === 0) return;
    const ids = Array.from(selected);
    const noun = ids.length === 1 ? "1 entry" : `${ids.length} entries`;
    if (!window.confirm(`Permanently delete ${noun}? This removes all records and files and cannot be undone.`)) return;
    setDeleting(true);
    try {
      await Promise.all(ids.map((id) => deleteApplication(id)));
      setApps((prev) => prev.filter((a) => !selected.has(a.applicationId)));
      setSelected(new Set());
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Delete failed";
      setError(msg);
    } finally {
      setDeleting(false);
    }
  }

  const statusToggles: { key: keyof EnabledGroups; label: string }[] = [
    { key: "processing", label: "Processing" },
    { key: "failed",     label: "Failed" },
    { key: "ready",      label: "Ready" },
    { key: "reviewed",   label: "Reviewed" },
  ];

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
        eyebrow={`${eyebrowDate} · ${today.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} CT`}
        title="Reviewer dashboard"
        subtitle={`${awaiting.length} applications awaiting review · ${highSeverity} high severity`}
      />

      <div
        style={{
          padding: "22px 34px 40px",
          display: "flex",
          flexDirection: "column",
          gap: 18,
        }}
      >
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
                background: t.surface,
                border: `1px solid ${t.line}`,
                borderTop: `3px solid ${s.accent}`,
                padding: "16px 18px",
                borderRadius: 3,
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  color: t.ink3,
                  letterSpacing: 0.4,
                  textTransform: "uppercase",
                  fontFamily: t.mono,
                }}
              >
                {s.label}
              </div>
              <div
                style={{
                  fontSize: 34,
                  fontWeight: 600,
                  fontFamily: t.serif,
                  color: t.ink,
                  marginTop: 4,
                  letterSpacing: -0.5,
                  lineHeight: 1,
                }}
              >
                {s.value}
              </div>
              <div style={{ fontSize: 11, color: t.ink4, marginTop: 8 }}>
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
              <Btn
                variant="ghost"
                size="sm"
                onClick={() => onNavigate("queue")}
              >
                View all &rarr;
              </Btn>
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
              <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
                {statusToggles.map(({ key, label }) => {
                  const active = enabledGroups[key];
                  return (
                    <button
                      key={key}
                      onClick={() => toggleGroup(key)}
                      style={{
                        fontSize: 10,
                        fontFamily: t.mono,
                        fontWeight: 700,
                        letterSpacing: 0.3,
                        textTransform: "uppercase",
                        padding: "3px 9px",
                        borderRadius: 2,
                        cursor: "pointer",
                        border: `1px solid ${active ? t.accent : t.line}`,
                        background: active ? t.accent : "transparent",
                        color: active ? "#fff" : t.ink3,
                        transition: "background 0.15s, color 0.15s",
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
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as SortKey)}
                  style={selectStyle}
                >
                  <option value="date_desc">Newest first</option>
                  <option value="date_asc">Oldest first</option>
                  <option value="status">By status</option>
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
                  {[
                    "Application",
                    "Applicant",
                    "Institution",
                    "Status",
                    "Age",
                    "Flags",
                    "",
                  ].map((h, i) => (
                    <th
                      key={i}
                      style={{
                        textAlign: "left",
                        padding: "9px 14px",
                        fontSize: 10,
                        letterSpacing: 0.5,
                        textTransform: "uppercase",
                        fontWeight: 600,
                        color: t.ink3,
                        fontFamily: t.mono,
                        borderBottom: `1px solid ${t.line}`,
                      }}
                    >
                      {h}
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
                  const target = applicationTarget(r);
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
                      onNavigate={navigate}
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
                  const target = applicationTarget(a);
                  return (
                    <div
                      key={a.applicationId}
                      onClick={() => target && navigate(target)}
                      onKeyDown={(e) => {
                        if (!target) return;
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          navigate(target);
                        }
                      }}
                      tabIndex={target ? 0 : undefined}
                      aria-label={
                        target ? `Open ${displayApplicant(a)}` : undefined
                      }
                      style={{
                        padding: "11px 18px",
                        borderBottom:
                          i < queue.length - 1
                            ? `1px solid ${t.line2}`
                            : "none",
                        display: "flex",
                        gap: 10,
                        alignItems: "flex-start",
                        cursor: target ? "pointer" : "default",
                      }}
                    >
                      <div
                        style={{
                          width: 6,
                          height: 6,
                          borderRadius: 3,
                          marginTop: 6,
                          background: t.accent,
                        }}
                      />
                      <div
                        style={{
                          flex: 1,
                          fontSize: 12,
                          color: t.ink2,
                          lineHeight: 1.5,
                        }}
                      >
                        <span style={{ fontWeight: 600, color: t.ink }}>
                          System
                        </span>{" "}
                        <span style={{ color: t.ink3 }}>
                          {isProcessing(a)
                            ? "started processing"
                            : a.status === "FAILED"
                              ? "failed"
                              : a.status === "REVIEWED"
                                ? "reviewed"
                                : "queued"}
                        </span>{" "}
                        <span
                          style={{
                            fontFamily: t.mono,
                            fontSize: 11,
                            color: t.ink2,
                          }}
                        >
                          {a.applicationId}
                        </span>
                        <div
                          style={{
                            fontSize: 10,
                            color: t.ink4,
                            fontFamily: t.mono,
                            marginTop: 2,
                            letterSpacing: 0.2,
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
              : r.status === "REVIEWED"
                ? "Audit →"
                : "Waiting"}
        </button>
      </td>
    </tr>
  );
}
