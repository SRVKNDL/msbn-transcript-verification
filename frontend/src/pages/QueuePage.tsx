import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useT } from "../theme";
import { PageHeader } from "../components/Shell";
import { SeverityChip } from "../components/SeverityChip";
import {
  applicationDetailPath,
  detailBackStateFor,
  hasApplicationSummary,
  isApplicationReviewable,
} from "../navigation";
import { listApplications } from "../api";
import type { Application } from "../types";

function timeAgo(hrs: number) {
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function fullTimestamp(hrs: number) {
  const d = new Date(Date.now() - hrs * 3600_000);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function isProcessing(app: Application) {
  return app.status === "PROCESSING" || app.status === "INTAKE_COMPLETE";
}

export function QueuePage() {
  const t = useT();
  const navigate = useNavigate();
  const navigateFromQueue = (path: string) => {
    navigate(path, detailBackStateFor("queue"));
  };
  const [apps, setApps] = useState<Application[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<"all" | "ready" | "processing">("all");
  const [severityFilter, setSeverityFilter] = useState<"all" | "high" | "medium" | "low" | "clean">("all");
  const [sortBy, setSortBy] = useState<"submitted" | "severity" | "flags" | "applicant" | "institution">("severity");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      listApplications({ statuses: ["PROCESSING", "INTAKE_COMPLETE", "READY_FOR_REVIEW"] })
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
    const interval = window.setInterval(load, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  const queueApps = apps.filter(
    (a) => isProcessing(a) || isApplicationReviewable(a)
  );
  const hiddenPendingCount = apps.filter(
    (a) => a.status === "READY_FOR_REVIEW" && !hasApplicationSummary(a)
  ).length;
  const normalizedQuery = query.trim().toLowerCase();
  const severityRank = { High: 0, Medium: 1, Low: 2 } as const;
  const shown = queueApps
    .filter((a) => {
      if (statusFilter === "ready" && !isApplicationReviewable(a)) return false;
      if (statusFilter === "processing" && !isProcessing(a)) return false;
      if (severityFilter === "high" && a.highestSeverity !== "High") return false;
      if (severityFilter === "medium" && a.highestSeverity !== "Medium") return false;
      if (severityFilter === "low" && a.highestSeverity !== "Low") return false;
      if (severityFilter === "clean" && a.flagCount !== 0) return false;
      if (!normalizedQuery) return true;
      return [
        a.applicationId,
        a.applicantName,
        a.institution,
        a.licenseNumber,
        a.country,
      ].join(" ").toLowerCase().includes(normalizedQuery);
    })
    .sort((a, b) => {
      if (sortBy === "submitted") return b.submittedAt.localeCompare(a.submittedAt);
      if (sortBy === "flags") return b.flagCount - a.flagCount || b.submittedAt.localeCompare(a.submittedAt);
      if (sortBy === "applicant") return (a.applicantName || a.originalFilename).localeCompare(b.applicantName || b.originalFilename);
      if (sortBy === "institution") return a.institution.localeCompare(b.institution);
      return (severityRank[a.highestSeverity ?? "Low"] ?? 3) - (severityRank[b.highestSeverity ?? "Low"] ?? 3)
        || b.flagCount - a.flagCount
        || b.submittedAt.localeCompare(a.submittedAt);
    });
  const subtitle = error
    ? `Unable to load queue: ${error}`
    : hiddenPendingCount > 0
      ? `${hiddenPendingCount} uploaded transcript${hiddenPendingCount === 1 ? "" : "s"} still waiting for extracted applicant data`
      : "Prioritized transcript applications ready for board review";

  return (
    <div
      style={{
        minHeight: "100%",
        background: t.bg,
        color: t.ink,
        display: "flex",
        flexDirection: "column",
      }}
    >
      <PageHeader
        eyebrow="Review queue"
        title={`${shown.length} applications in queue`}
        subtitle={subtitle}
        actions={
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter queue"
              aria-label="Filter queue"
              style={{
                height: 30,
                width: 180,
                border: `1px solid ${t.line}`,
                background: t.surface,
                color: t.ink2,
                borderRadius: 3,
                padding: "0 9px",
                fontSize: 12,
                fontFamily: "inherit",
              }}
            />
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}
              style={{ height: 30, border: `1px solid ${t.line}`, background: t.surface, color: t.ink2, borderRadius: 3, padding: "0 8px", fontSize: 12, fontFamily: t.mono }}
            >
              <option value="all">All statuses</option>
              <option value="ready">Ready</option>
              <option value="processing">Processing</option>
            </select>
            <select
              value={severityFilter}
              onChange={(event) => setSeverityFilter(event.target.value as typeof severityFilter)}
              style={{ height: 30, border: `1px solid ${t.line}`, background: t.surface, color: t.ink2, borderRadius: 3, padding: "0 8px", fontSize: 12, fontFamily: t.mono }}
            >
              <option value="all">All severities</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
              <option value="clean">No flags</option>
            </select>
            <select
              value={sortBy}
              onChange={(event) => setSortBy(event.target.value as typeof sortBy)}
              style={{ height: 30, border: `1px solid ${t.line}`, background: t.surface, color: t.ink2, borderRadius: 3, padding: "0 8px", fontSize: 12, fontFamily: t.mono }}
            >
              <option value="severity">Severity</option>
              <option value="submitted">Newest</option>
              <option value="flags">Most flags</option>
              <option value="applicant">Applicant</option>
              <option value="institution">Institution</option>
            </select>
          </div>
        }
      />

      {/* Bulk action bar */}
      {selected.size > 0 && (
        <div
          style={{
            margin: "22px 34px 0",
            padding: "8px 16px",
            background: t.accent,
            borderRadius: "3px 3px 0 0",
            display: "flex",
            alignItems: "center",
            gap: 12,
            color: t.primaryInk,
            fontSize: 12,
            fontFamily: t.mono,
          }}
        >
          <span>{selected.size} selected</span>
          <button
            onClick={() => setSelected(new Set())}
            style={{
              border: "none",
              background: "transparent",
              color: "rgba(255,255,255,0.7)",
              padding: "4px 10px",
              fontSize: 11,
              cursor: "pointer",
              fontFamily: "inherit",
            }}
          >
            Clear selection
          </button>
        </div>
      )}

      {/* Table */}
      <div
        style={{
          flex: 1,
          overflow: "auto",
          padding: selected.size > 0 ? "0 34px 40px" : "22px 34px 40px",
        }}
      >
        <div
          style={{
            background: t.surface,
            border: `1px solid ${t.line}`,
            borderRadius: selected.size > 0 ? "0 0 3px 3px" : 3,
            overflow: "hidden",
          }}
        >
          {/* Header row */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "24px 14px 1.4fr 1.2fr 100px 140px 100px 90px",
              gap: 14,
              alignItems: "center",
              padding: "10px 16px",
              borderBottom: `1px solid ${t.line}`,
              background: t.surfaceAlt,
              fontSize: 10,
              color: t.ink3,
              letterSpacing: 0.5,
              textTransform: "uppercase",
              fontFamily: t.mono,
            }}
          >
            <input
              type="checkbox"
              checked={selected.size === shown.length && shown.length > 0}
              onChange={(e) => {
                if (e.target.checked) setSelected(new Set(shown.map((a) => a.applicationId)));
                else setSelected(new Set());
              }}
              style={{ width: 14, height: 14, cursor: "pointer" }}
            />
            <div />
            <div>Applicant</div>
            <div>Institution</div>
            <div>License</div>
            <div>Flags</div>
            <div>Submitted</div>
            <div />
          </div>

          {/* Rows */}
          {shown.length === 0 && (
            <div
              style={{
                padding: "48px 24px",
                textAlign: "center",
                color: t.ink4,
              }}
            >
              <div style={{ fontSize: 28, marginBottom: 8, opacity: 0.4 }}>&#9744;</div>
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 500,
                  color: t.ink3,
                  marginBottom: 4,
                }}
              >
                {error ? "Queue failed to load" : "No applications match this filter"}
              </div>
              <div style={{ fontSize: 12 }}>
                {error
                  ? "Refresh after the API issue is resolved."
                  : "Try a different filter or check back later."}
              </div>
            </div>
          )}
          {shown.map((app, i) => {
            const target = applicationDetailPath(app, "queue");
            return (
            <div
              key={app.applicationId}
              onClick={() => {
                if (target) navigateFromQueue(target);
              }}
              onMouseEnter={(e) => {
                if (target) e.currentTarget.style.background = t.surfaceAlt;
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = selected.has(app.applicationId) ? t.surfaceAlt : "transparent";
              }}
              style={{
                display: "grid",
                gridTemplateColumns: "24px 14px 1.4fr 1.2fr 100px 140px 100px 90px",
                gap: 14,
                alignItems: "center",
                padding: "12px 16px",
                borderBottom:
                  i < shown.length - 1
                    ? `1px solid ${t.line2}`
                    : "none",
                cursor: target ? "pointer" : "default",
                fontSize: 13,
                color: t.ink2,
                transition: "background 120ms",
              }}
            >
              <input
                type="checkbox"
                checked={selected.has(app.applicationId)}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => {
                  const next = new Set(selected);
                  if (e.target.checked) next.add(app.applicationId);
                  else next.delete(app.applicationId);
                  setSelected(next);
                }}
                style={{ width: 14, height: 14, cursor: "pointer" }}
              />
              <div
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: 3,
                  background:
                    app.highestSeverity === "High"
                      ? t.high
                      : app.highestSeverity === "Medium"
                        ? t.med
                        : app.highestSeverity === "Low"
                          ? t.low
                          : t.line,
                }}
              />
              <div>
                <div style={{ fontWeight: 500, color: t.ink }}>
                  {app.applicantName}
                </div>
                <div
                  style={{
                    fontSize: 11,
                    color: t.ink4,
                    fontFamily: t.mono,
                    marginTop: 1,
                  }}
                >
                  #{app.applicationId}
                </div>
              </div>
              <div style={{ fontSize: 12 }}>
                <div>{app.institution}</div>
                <div style={{ fontSize: 11, color: t.ink4 }}>
                  {app.country}
                </div>
              </div>
              <div
                style={{
                  fontFamily: t.mono,
                  fontSize: 12,
                }}
              >
                {app.licenseNumber}
              </div>
              <div
                style={{ display: "flex", alignItems: "center", gap: 8 }}
              >
                <span
                  style={{
                    fontFamily: t.mono,
                    fontSize: 12,
                    minWidth: 12,
                  }}
                >
                  {isProcessing(app) ? "..." : app.flagCount}
                </span>
                {isProcessing(app) ? (
                  <span style={{ fontSize: 11, color: t.ink4, fontFamily: t.mono }}>
                    processing
                  </span>
                ) : (
                  <SeverityChip severity={app.highestSeverity} />
                )}
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: t.ink3,
                  fontFamily: t.mono,
                  cursor: "help",
                }}
                title={fullTimestamp(app.ageHours)}
              >
                {timeAgo(app.ageHours)}
              </div>
              <div style={{ textAlign: "right" }}>
                <button
                  disabled={!target}
                  style={{
                    border: `1px solid ${t.line}`,
                    background: t.surfaceAlt,
                    padding: "4px 10px",
                    fontSize: 11,
                    borderRadius: 2,
                    fontFamily: t.mono,
                    color: target ? t.ink2 : t.ink4,
                    cursor: target ? "pointer" : "default",
                  }}
                >
                  {isProcessing(app) ? "waiting" : "open \u2192"}
                </button>
              </div>
            </div>
          );
          })}
        </div>
      </div>
    </div>
  );
}
