import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useT } from "../theme";
import { PageHeader, Card } from "../components/Shell";
import {
  applicationAuditPath,
  applicationReviewPath,
  detailBackStateFor,
} from "../navigation";
import { getAuditTrail } from "../api";
import {
  auditStageForEvent,
  auditStageStyle,
  formatAuditTimestamp,
  humanizeAuditEvent,
} from "../auditUi";
import type { Application, AuditEvent } from "../types";
import { useApplicationList } from "../useApplicationList";

function SeverityDot({ severity }: { severity: string }) {
  const t = useT();
  const color =
    severity === "High" ? t.high : severity === "Medium" ? t.med : t.low;
  return (
    <span
      style={{
        display: "inline-block",
        width: 8,
        height: 8,
        borderRadius: 4,
        background: color,
        marginRight: 6,
      }}
    />
  );
}

function EventRow({ event }: { event: AuditEvent }) {
  const t = useT();
  const stage = auditStageForEvent(event);
  const stageStyle = auditStageStyle(stage, t);
  const timestamp = formatAuditTimestamp(event.ts);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        gap: 10,
        padding: "7px 0",
        fontSize: 12,
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: 4,
          background: stageStyle.color,
          flexShrink: 0,
          alignSelf: "center",
        }}
      />
      <span
        style={{
          fontFamily: t.mono,
          fontSize: 10,
          color: t.ink4,
          minWidth: 130,
          flexShrink: 0,
        }}
      >
        {timestamp.compact}
      </span>
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: t.mono,
          fontSize: 10,
          fontWeight: 800,
          color: stageStyle.color,
          background: stageStyle.background,
          border: `1px solid ${stageStyle.border}`,
          borderRadius: 999,
          padding: "3px 8px",
          minWidth: 120,
          flexShrink: 0,
          textTransform: "uppercase",
          letterSpacing: 0.4,
        }}
      >
        {stageStyle.label}
      </span>
      <span style={{ color: stageStyle.color, fontFamily: t.mono, fontSize: 11, fontWeight: 800 }}>
        {humanizeAuditEvent(event.event)}
      </span>
      <span style={{ color: t.ink3, fontSize: 12 }}>{event.detail}</span>
    </div>
  );
}

export function AuditOverviewPage() {
  const t = useT();
  const navigate = useNavigate();
  const navigateFromAuditLog = (path: string) => {
    navigate(path, detailBackStateFor("audit"));
  };
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [eventFilter, setEventFilter] = useState<"all" | "flags_only" | "review" | "system">("all");
  const [severityFilter, setSeverityFilter] = useState<"all" | "high" | "medium" | "low">("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "ready" | "reviewed" | "failed" | "processing">("all");
  const [query, setQuery] = useState("");
  const { apps: loadedApps } = useApplicationList({
    statuses: [
      "PROCESSING",
      "INTAKE_COMPLETE",
      "READY_FOR_REVIEW",
      "FAILED",
      "REVIEWED",
      "READY_FOR_LICENSING_REVIEW",
      "RETURN_TO_APPLICANT",
      "DEFERRED",
      "DENIED",
      "APPROVED",
      "CLOSED",
      "COMPLETED",
    ],
    limit: 200,
    pollMs: 15000,
  });
  const [audits, setAudits] = useState<Record<string, AuditEvent[]>>({});
  const [loadingAudits, setLoadingAudits] = useState<Record<string, boolean>>({});
  const [auditErrors, setAuditErrors] = useState<Record<string, string>>({});
  const apps = [...loadedApps].sort(
    (a, b) => new Date(b.submittedAt).getTime() - new Date(a.submittedAt).getTime()
  );

  function hasLoadedAudit(applicationId: string) {
    return Object.prototype.hasOwnProperty.call(audits, applicationId);
  }

  function loadAuditEvents(applicationId: string) {
    if (hasLoadedAudit(applicationId) || loadingAudits[applicationId]) return;

    setLoadingAudits((current) => ({ ...current, [applicationId]: true }));
    setAuditErrors((current) => {
      const next = { ...current };
      delete next[applicationId];
      return next;
    });

    getAuditTrail(applicationId)
      .then((events) => {
        setAudits((current) => ({ ...current, [applicationId]: events }));
      })
      .catch((err) => {
        setAuditErrors((current) => ({
          ...current,
          [applicationId]:
            err instanceof Error ? err.message : "Unable to load audit events.",
        }));
      })
      .finally(() => {
        setLoadingAudits((current) => {
          const next = { ...current };
          delete next[applicationId];
          return next;
        });
      });
  }

  function toggleExpanded(app: Application) {
    const nextExpandedId = expandedId === app.applicationId ? null : app.applicationId;
    setExpandedId(nextExpandedId);
    if (nextExpandedId) loadAuditEvents(app.applicationId);
  }

  const totalEvents = apps.reduce(
    (sum, app) => sum + (audits[app.applicationId]?.length ?? 0),
    0
  );
  const normalizedQuery = query.trim().toLowerCase();
  const filteredApps = apps.filter((app) => {
    if (statusFilter === "ready" && app.status !== "READY_FOR_REVIEW") return false;
    if (statusFilter === "reviewed" && app.status !== "REVIEWED") return false;
    if (statusFilter === "failed" && app.status !== "FAILED") return false;
    if (statusFilter === "processing" && app.status !== "PROCESSING" && app.status !== "INTAKE_COMPLETE") return false;
    if (severityFilter !== "all" && app.highestSeverity?.toLowerCase() !== severityFilter) return false;
    if (!normalizedQuery) return true;
    return [
      app.applicationId,
      app.applicantName,
      app.institution,
      app.country,
      app.licenseNumber,
    ].join(" ").toLowerCase().includes(normalizedQuery);
  });

  function filterEvents(events: AuditEvent[]) {
    if (eventFilter === "flags_only") return events.filter((e) => e.event === "FLAG_RAISED");
    if (eventFilter === "review") return events.filter((e) => /review|decision|approved|denied|returned/i.test(`${e.event} ${e.detail}`));
    if (eventFilter === "system") return events.filter((e) => e.actor === "system" || /status|processing|intake/i.test(e.event));
    return events;
  }

  return (
    <>
      <PageHeader
        eyebrow="SP-9 \u00b7 Compliance"
        title="Audit log"
        subtitle={`${filteredApps.length} of ${apps.length} documents \u00b7 ${totalEvents} loaded events`}
        actions={
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter audit log"
              aria-label="Filter audit log"
              style={{
                height: 30,
                width: 180,
                border: `1px solid ${t.line}`,
                background: t.surfaceAlt,
                color: t.ink2,
                borderRadius: 3,
                padding: "0 9px",
                fontSize: 12,
                fontFamily: "inherit",
              }}
            />
            <select
              value={eventFilter}
              onChange={(e) => setEventFilter(e.target.value as typeof eventFilter)}
              style={{
                padding: "6px 10px",
                background: t.surfaceAlt,
                border: `1px solid ${t.line}`,
                borderRadius: 3,
                fontSize: 12,
                color: t.ink2,
                fontFamily: t.mono,
                cursor: "pointer",
              }}
            >
              <option value="all">All events</option>
              <option value="flags_only">Flags only</option>
              <option value="review">Review events</option>
              <option value="system">System events</option>
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
              style={{
                padding: "6px 10px",
                background: t.surfaceAlt,
                border: `1px solid ${t.line}`,
                borderRadius: 3,
                fontSize: 12,
                color: t.ink2,
                fontFamily: t.mono,
                cursor: "pointer",
              }}
            >
              <option value="all">All statuses</option>
              <option value="ready">Ready</option>
              <option value="reviewed">Reviewed</option>
              <option value="failed">Failed</option>
              <option value="processing">Processing</option>
            </select>
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value as typeof severityFilter)}
              style={{
                padding: "6px 10px",
                background: t.surfaceAlt,
                border: `1px solid ${t.line}`,
                borderRadius: 3,
                fontSize: 12,
                color: t.ink2,
                fontFamily: t.mono,
                cursor: "pointer",
              }}
            >
              <option value="all">All severities</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
        }
      />

      <div style={{ padding: "20px 34px 40px", maxWidth: 960 }}>
        {filteredApps.map((app) => {
          const auditLoaded = hasLoadedAudit(app.applicationId);
          const auditLoading = Boolean(loadingAudits[app.applicationId]);
          const auditError = auditErrors[app.applicationId];
          const allEvents = audits[app.applicationId] ?? [];
          const events = filterEvents(allEvents);
          const isExpanded = expandedId === app.applicationId;
          const flagCount = auditLoaded
            ? allEvents.filter((e) => e.event === "FLAG_RAISED").length
            : app.flagCount;

          return (
            <div key={app.applicationId} style={{ marginBottom: 10 }}>
              <Card pad={0}>
                {/* Row header */}
                <div
                  onClick={() => toggleExpanded(app)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 14,
                    padding: "14px 18px",
                    cursor: "pointer",
                    userSelect: "none",
                  }}
                >
                  <span
                    style={{
                      fontSize: 12,
                      color: t.ink3,
                      width: 16,
                      fontFamily: t.mono,
                    }}
                  >
                    {isExpanded ? "\u25bc" : "\u25b6"}
                  </span>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span
                        style={{
                          fontSize: 14,
                          fontWeight: 600,
                          fontFamily: t.serif,
                          color: t.ink,
                        }}
                      >
                        {app.applicantName}
                      </span>
                      <span
                        style={{
                          fontSize: 11,
                          color: t.ink4,
                          fontFamily: t.mono,
                        }}
                      >
                        #{app.applicationId}
                      </span>
                      {app.highestSeverity && (
                        <SeverityDot severity={app.highestSeverity} />
                      )}
                    </div>
                    <div
                      style={{
                        fontSize: 12,
                        color: t.ink3,
                        marginTop: 2,
                      }}
                    >
                      {app.institution} &middot; {app.country}
                    </div>
                  </div>
                  <div
                    style={{
                      textAlign: "right",
                      fontSize: 11,
                      fontFamily: t.mono,
                    }}
                  >
                    <div style={{ color: t.ink3 }}>
                      {auditLoaded ? `${allEvents.length} events` : "Events on demand"}
                      {flagCount > 0 && (
                        <span style={{ color: t.high, marginLeft: 8 }}>
                          {flagCount} flags
                        </span>
                      )}
                    </div>
                    <div style={{ color: t.ink4, marginTop: 2 }}>
                      {new Date(app.submittedAt).toLocaleDateString()}
                    </div>
                  </div>
                </div>

                {/* Expanded event list */}
                {isExpanded && (
                  <div
                    style={{
                      borderTop: `1px solid ${t.line2}`,
                      padding: "12px 18px 14px 48px",
                      background: t.surfaceAlt,
                    }}
                  >
                    {auditLoading ? (
                      <div
                        style={{
                          fontSize: 12,
                          color: t.ink4,
                          fontStyle: "italic",
                        }}
                      >
                        Loading audit events...
                      </div>
                    ) : auditError ? (
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 10,
                          fontSize: 12,
                          color: t.high,
                        }}
                      >
                        <span>{auditError}</span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            loadAuditEvents(app.applicationId);
                          }}
                          style={{
                            background: t.surface,
                            border: `1px solid ${t.line}`,
                            padding: "4px 10px",
                            fontSize: 11,
                            borderRadius: 2,
                            cursor: "pointer",
                            fontFamily: t.mono,
                            color: t.ink2,
                          }}
                        >
                          Retry
                        </button>
                      </div>
                    ) : events.length === 0 ? (
                      <div
                        style={{
                          fontSize: 12,
                          color: t.ink4,
                          fontStyle: "italic",
                        }}
                      >
                        No matching events.
                      </div>
                    ) : (
                      events.map((e, i) => <EventRow key={i} event={e} />)
                    )}

                    <div
                      style={{
                        marginTop: 10,
                        paddingTop: 10,
                        borderTop: `1px solid ${t.line}`,
                        display: "flex",
                        gap: 10,
                      }}
                    >
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          navigateFromAuditLog(applicationAuditPath(app));
                        }}
                        style={{
                          background: t.surface,
                          border: `1px solid ${t.line}`,
                          padding: "5px 12px",
                          fontSize: 11,
                          borderRadius: 2,
                          cursor: "pointer",
                          fontFamily: t.mono,
                          color: t.ink2,
                        }}
                      >
                        View full timeline &rarr;
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          navigateFromAuditLog(applicationReviewPath(app));
                        }}
                        style={{
                          background: t.surface,
                          border: `1px solid ${t.line}`,
                          padding: "5px 12px",
                          fontSize: 11,
                          borderRadius: 2,
                          cursor: "pointer",
                          fontFamily: t.mono,
                          color: t.ink2,
                        }}
                      >
                        Open review
                      </button>
                    </div>
                  </div>
                )}
              </Card>
            </div>
          );
        })}
      </div>
    </>
  );
}
