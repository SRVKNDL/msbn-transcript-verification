import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { CSSProperties } from "react";
import { getApplication, getAuditTrail } from "../api";
import { getCurrentUser } from "../auth";
import {
  auditStageForEvent,
  auditStageStyle,
  auditTimeValue,
  formatAuditTimestamp,
  humanizeAuditEvent,
  type AuditStage,
} from "../auditUi";
import { useT } from "../theme";
import type { Application, AuditEvent, Flag } from "../types";

interface TimelineItem {
  id: string;
  ts: string;
  title: string;
  detail: string;
  actor: string;
  stage: AuditStage;
  sequence: number;
}

function formatStatusLabel(status: string) {
  return status
    .split("_")
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1).toLowerCase()}`)
    .join(" ");
}

function hasReviewOutcome(app: Application | null, events: AuditEvent[]) {
  const status = app?.status.toLowerCase() ?? "";
  if (/\b(reviewed|approved|denied|returned|closed|completed|licensing)\b/.test(status)) {
    return true;
  }
  return events.some((event) => {
    const text = `${event.event} ${event.detail}`.toLowerCase();
    return (
      /\b(decision|reviewed|approved|denied|returned)\b/.test(text) ||
      (/\bsubmitted\b/.test(text) && /\b(review|decision)\b/.test(text))
    );
  });
}

function auditTitle(event: AuditEvent) {
  if (event.event === "STATUS_CHANGED") return "Processing Status Updated";
  if (event.event === "AUDIT_EVENT") return "Audit Event Recorded";
  return humanizeAuditEvent(event.event);
}

function auditDetail(event: AuditEvent, app: Application | null) {
  if (event.detail.trim()) return event.detail;
  if (event.event === "STATUS_CHANGED") {
    return app?.status
      ? `Current application status: ${formatStatusLabel(app.status)}`
      : "Automated processing checkpoint recorded.";
  }
  return event.actor === "system"
    ? "Automated system activity recorded."
    : `Recorded by ${event.actor}.`;
}

function groupedFlagItems(flags: Flag[]) {
  const groups = new Map<string, Flag[]>();
  flags.forEach((flag) => {
    const existing = groups.get(flag.ruleCode) ?? [];
    existing.push(flag);
    groups.set(flag.ruleCode, existing);
  });
  return Array.from(groups.entries()).sort(([a], [b]) => a.localeCompare(b));
}

function flagSeverityRank(severity: Flag["severity"]) {
  if (severity === "High") return 0;
  if (severity === "Medium") return 1;
  return 2;
}

function flagGroupDetail(ruleFlags: Flag[]) {
  const highestSeverity =
    [...ruleFlags].sort((a, b) => flagSeverityRank(a.severity) - flagSeverityRank(b.severity))[0]?.severity ??
    "Low";
  const pages = Array.from(
    new Set(ruleFlags.map((flag) => flag.sourceLocation.page).filter(Boolean))
  ).sort((a, b) => a - b);
  const pageLabel =
    pages.length > 0 ? `page${pages.length === 1 ? "" : "s"} ${pages.join(", ")}` : "source page unavailable";
  return `${ruleFlags.length} flag${ruleFlags.length === 1 ? "" : "s"} - ${highestSeverity} - ${pageLabel}`;
}

function buildTimelineItems(app: Application | null, events: AuditEvent[], flags: Flag[]) {
  const sorted = [...events].sort((a, b) => auditTimeValue(a.ts) - auditTimeValue(b.ts));
  const hasCreationEvent = sorted.some((event) => auditStageForEvent(event) === "created");
  const hasFlagAuditEvents = sorted.some((event) => auditStageForEvent(event) === "flag");
  const items: TimelineItem[] = [];

  if (app && !hasCreationEvent) {
    items.push({
      id: "submitted-at",
      ts: app.submittedAt,
      title: "Application Created",
      detail: app.originalFilename || app.institution,
      actor: "system",
      stage: "created",
      sequence: 0,
    });
  }

  sorted.forEach((event, index) => {
    items.push({
      id: `${event.ts}-${event.event}-${index}`,
      ts: event.ts,
      title: auditTitle(event),
      detail: auditDetail(event, app),
      actor: event.actor,
      stage: auditStageForEvent(event),
      sequence: 20 + index,
    });
  });

  if (flags.length > 0 && !hasFlagAuditEvents) {
    const flagTs =
      sorted.find((event) => auditStageForEvent(event) === "processing")?.ts ||
      sorted[0]?.ts ||
      app?.submittedAt ||
      "";

    groupedFlagItems(flags).forEach(([ruleCode, ruleFlags], index) => {
      items.push({
        id: `flag-${ruleCode}`,
        ts: flagTs,
        title: `${ruleCode} Flag Raised`,
        detail: flagGroupDetail(ruleFlags),
        actor: "rule engine",
        stage: "flag",
        sequence: 80 + index,
      });
    });
  }

  return items.sort((a, b) => auditTimeValue(a.ts) - auditTimeValue(b.ts) || a.sequence - b.sequence);
}

function clampTextStyle(lines: number): CSSProperties {
  return {
    display: "-webkit-box",
    WebkitBoxOrient: "vertical",
    WebkitLineClamp: lines,
    overflow: "hidden",
  };
}

export function AuditPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const t = useT();
  const user = getCurrentUser();
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [flags, setFlags] = useState<Flag[]>([]);
  const [app, setApp] = useState<Application | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;

    let cancelled = false;
    setIsLoading(true);
    setError(null);
    setEvents([]);
    setFlags([]);
    setApp(null);

    Promise.all([getAuditTrail(id), getApplication(id)])
      .then(([trail, data]) => {
        if (cancelled) return;
        setEvents(trail);
        setFlags(data.flags);
        setApp(data.application);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Unable to load audit trail.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [id]);

  const timelineItems = useMemo(() => buildTimelineItems(app, events, flags), [app, events, flags]);
  const reviewed = hasReviewOutcome(app, events);
  const terminalStage = reviewed ? "review" : "system";
  const terminalStyle = auditStageStyle(terminalStage, t);
  const timelineMinWidth = Math.max(840, (timelineItems.length + 1) * 170);
  const legendStages: AuditStage[] = ["created", "processing", "flag", "review", "system"];

  return (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        background: t.bg,
        color: t.ink,
        fontFamily: t.sans,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <header
        style={{
          height: 60,
          flexShrink: 0,
          background: t.primary,
          color: t.primaryInk,
          display: "flex",
          alignItems: "center",
          padding: "0 22px",
          gap: 16,
          borderBottom: `3px solid ${t.accent}`,
        }}
      >
        <button
          onClick={() => navigate("/audit")}
          title="Back to audit log"
          aria-label="Back to audit log"
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
          }}
        >
          &larr;
        </button>
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
          <div style={{ fontSize: 14, fontWeight: 600, fontFamily: t.serif }}>
            Audit Timeline
          </div>
        </div>
        <div
          style={{
            height: 28,
            width: 1,
            background: "rgba(255,255,255,0.18)",
            marginLeft: 4,
          }}
        />
        <button
          onClick={() => navigate("/dashboard")}
          style={{
            border: "1px solid rgba(255,255,255,0.18)",
            background: "rgba(255,255,255,0.08)",
            color: "inherit",
            borderRadius: 3,
            padding: "7px 12px",
            fontFamily: t.mono,
            fontSize: 11,
            cursor: "pointer",
          }}
        >
          &larr; Dashboard
        </button>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 12, opacity: 0.85 }}>
          {user?.email ?? "Reviewer account"}
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
      </header>

      <main style={{ flex: 1, overflow: "auto", padding: "24px 34px 44px" }}>
        <section
          style={{
            maxWidth: 1180,
            margin: "0 auto 16px",
            display: "grid",
            gridTemplateColumns: "minmax(0, 1fr) auto",
            gap: 18,
            alignItems: "end",
          }}
        >
          <div>
            <div
              style={{
                fontFamily: t.mono,
                fontSize: 11,
                color: t.ink4,
                letterSpacing: 1,
                textTransform: "uppercase",
                marginBottom: 6,
              }}
            >
              SP-9 Compliance Trail
            </div>
            <h1
              style={{
                margin: 0,
                fontFamily: t.serif,
                fontSize: 24,
                letterSpacing: 0,
                lineHeight: 1.2,
                color: t.ink,
              }}
            >
              {app?.applicantName ?? "Application"}
            </h1>
            <div style={{ marginTop: 5, color: t.ink3, fontSize: 13 }}>
              #{id} {app?.institution ? `- ${app.institution}` : ""}
            </div>
          </div>
          <div
            style={{
              display: "flex",
              gap: 8,
              flexWrap: "wrap",
              justifyContent: "flex-end",
            }}
          >
            {legendStages.map((stage) => {
              const stageStyle = auditStageStyle(stage, t);
              return (
                <span
                  key={stage}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    border: `1px solid ${stageStyle.border}`,
                    background: stageStyle.background,
                    color: stageStyle.color,
                    borderRadius: 999,
                    padding: "5px 9px",
                    fontFamily: t.mono,
                    fontSize: 10,
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: 0.4,
                  }}
                >
                  <span
                    style={{
                      width: 7,
                      height: 7,
                      borderRadius: 4,
                      background: stageStyle.color,
                    }}
                  />
                  {stageStyle.label}
                </span>
              );
            })}
          </div>
        </section>

        <section
          style={{
            maxWidth: 1180,
            margin: "0 auto",
            background: t.surface,
            border: `1px solid ${t.line}`,
            borderRadius: 6,
            boxShadow: "0 14px 36px rgba(15, 23, 42, 0.08)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              padding: "16px 18px",
              borderBottom: `1px solid ${t.line}`,
              display: "flex",
              alignItems: "center",
              gap: 14,
              justifyContent: "space-between",
            }}
          >
            <div>
              <div style={{ fontFamily: t.serif, fontSize: 15, fontWeight: 700 }}>
                Timeline
              </div>
              <div style={{ marginTop: 2, fontSize: 12, color: t.ink3 }}>
                Chronological audit events from intake through reviewer action.
              </div>
            </div>
            <div
              style={{
                fontFamily: t.mono,
                fontSize: 11,
                color: t.ink4,
                textTransform: "uppercase",
                letterSpacing: 0.8,
              }}
            >
              {events.length} audit events · {flags.length} flags
            </div>
          </div>

          {error ? (
            <div style={{ padding: 20, color: t.high, fontSize: 13 }}>{error}</div>
          ) : isLoading ? (
            <div style={{ padding: 20, color: t.ink3, fontSize: 13 }}>
              Loading audit timeline...
            </div>
          ) : (
            <div style={{ overflowX: "auto", padding: "24px 18px 10px" }}>
              <div
                style={{
                  position: "relative",
                  minWidth: timelineMinWidth,
                  height: 260,
                  display: "grid",
                  gridTemplateColumns: `repeat(${timelineItems.length + 1}, minmax(150px, 1fr))`,
                  alignItems: "center",
                }}
              >
                <div
                  style={{
                    position: "absolute",
                    left: 68,
                    right: 68,
                    top: "50%",
                    height: 2,
                    background: `linear-gradient(90deg, ${t.line}, ${t.ink4}, ${reviewed ? t.ok : t.line})`,
                    transform: "translateY(-50%)",
                  }}
                />

                {timelineItems.map((item, index) => {
                  const stageStyle = auditStageStyle(item.stage, t);
                  const timestamp = formatAuditTimestamp(item.ts);
                  const isAbove = index % 2 === 0;

                  return (
                    <div key={item.id} style={{ position: "relative", height: "100%" }}>
                      <div
                        style={{
                          position: "absolute",
                          left: "50%",
                          top: "50%",
                          width: 16,
                          height: 16,
                          borderRadius: 8,
                          background: t.surface,
                          border: `3px solid ${stageStyle.color}`,
                          transform: "translate(-50%, -50%)",
                          boxShadow: `0 0 0 5px ${stageStyle.background}`,
                          zIndex: 2,
                        }}
                      />
                      <div
                        style={{
                          position: "absolute",
                          left: "50%",
                          top: isAbove ? "calc(50% - 58px)" : "calc(50% + 10px)",
                          height: 48,
                          borderLeft: `2px solid ${stageStyle.color}`,
                          opacity: 0.65,
                        }}
                      />
                      <div
                        style={{
                          position: "absolute",
                          left: "50%",
                          top: isAbove ? 0 : "calc(50% + 58px)",
                          transform: "translateX(-50%)",
                          width: 148,
                          minHeight: 70,
                          background: stageStyle.background,
                          border: `1px solid ${stageStyle.border}`,
                          borderRadius: 6,
                          padding: "9px 10px",
                          boxShadow: "0 10px 22px rgba(15, 23, 42, 0.08)",
                        }}
                      >
                        <div
                          style={{
                            fontFamily: t.mono,
                            fontSize: 10,
                            color: stageStyle.color,
                            fontWeight: 700,
                            textTransform: "uppercase",
                            letterSpacing: 0.4,
                          }}
                        >
                          {timestamp.time}
                        </div>
                        <div
                          style={{
                            marginTop: 4,
                            color: stageStyle.color,
                            fontSize: 12,
                            fontWeight: 800,
                            lineHeight: 1.25,
                            ...clampTextStyle(2),
                          }}
                        >
                          {item.title}
                        </div>
                        <div
                          title={item.detail}
                          style={{
                            marginTop: 5,
                            color: t.ink3,
                            fontSize: 11,
                            lineHeight: 1.35,
                            ...clampTextStyle(2),
                          }}
                        >
                          {item.detail || item.actor}
                        </div>
                      </div>
                    </div>
                  );
                })}

                <div style={{ position: "relative", height: "100%" }}>
                  <div
                    style={{
                      position: "absolute",
                      left: "50%",
                      top: "50%",
                      width: 17,
                      height: 17,
                      borderRadius: 10,
                      background: reviewed ? terminalStyle.color : t.surface,
                      border: reviewed
                        ? `3px solid ${terminalStyle.color}`
                        : `2px dashed ${t.ink4}`,
                      transform: "translate(-50%, -50%)",
                      boxShadow: reviewed ? `0 0 0 5px ${terminalStyle.background}` : "none",
                      zIndex: 2,
                    }}
                  />
                  <div
                    style={{
                      position: "absolute",
                      left: "50%",
                      top: "calc(50% - 58px)",
                      height: 48,
                      borderLeft: reviewed
                        ? `2px solid ${terminalStyle.color}`
                        : `2px dashed ${t.ink4}`,
                      opacity: 0.75,
                    }}
                  />
                  <div
                    style={{
                      position: "absolute",
                      left: "50%",
                      top: 0,
                      transform: "translateX(-50%)",
                      width: 148,
                      minHeight: 70,
                      background: terminalStyle.background,
                      border: `1px solid ${terminalStyle.border}`,
                      borderRadius: 6,
                      padding: "9px 10px",
                      boxShadow: "0 10px 22px rgba(15, 23, 42, 0.08)",
                    }}
                  >
                    <div
                      style={{
                        fontFamily: t.mono,
                        fontSize: 10,
                        color: terminalStyle.color,
                        fontWeight: 700,
                        textTransform: "uppercase",
                        letterSpacing: 0.4,
                      }}
                    >
                      {reviewed ? "Closed" : "Pending"}
                    </div>
                    <div
                      style={{
                        marginTop: 4,
                        color: terminalStyle.color,
                        fontSize: 12,
                        fontWeight: 800,
                        lineHeight: 1.25,
                      }}
                    >
                      {reviewed ? "Reviewed" : "Waiting for Reviewer"}
                    </div>
                    <div style={{ marginTop: 5, color: t.ink3, fontSize: 11, lineHeight: 1.35 }}>
                      {reviewed ? "Final action recorded." : "Decision has not been submitted."}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>

        <section
          style={{
            maxWidth: 1180,
            margin: "18px auto 0",
            background: t.surface,
            border: `1px solid ${t.line}`,
            borderRadius: 6,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              padding: "14px 18px",
              borderBottom: `1px solid ${t.line}`,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div style={{ fontFamily: t.serif, fontSize: 15, fontWeight: 700 }}>
              Event Details
            </div>
            <button
              onClick={() => navigate(`/review/${id}`)}
              style={{
                background: t.surfaceAlt,
                border: `1px solid ${t.line}`,
                borderRadius: 3,
                color: t.ink2,
                cursor: "pointer",
                fontFamily: t.mono,
                fontSize: 11,
                padding: "6px 10px",
              }}
            >
              Open review
            </button>
          </div>

          {timelineItems.length === 0 ? (
            <div style={{ padding: 18, color: t.ink4, fontSize: 13 }}>
              No audit events have been recorded for this application.
            </div>
          ) : (
            <div>
              {timelineItems.map((item, index) => {
                const stageStyle = auditStageStyle(item.stage, t);
                const timestamp = formatAuditTimestamp(item.ts);

                return (
                  <div
                    key={`${item.id}-detail`}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "170px 160px minmax(0, 1fr)",
                      gap: 16,
                      padding: "13px 18px",
                      borderTop: index === 0 ? "none" : `1px solid ${t.line2}`,
                      borderLeft: `4px solid ${stageStyle.color}`,
                      background: index % 2 === 0 ? t.surface : t.surfaceAlt,
                      alignItems: "start",
                    }}
                  >
                    <div>
                      <div style={{ fontFamily: t.mono, color: t.ink2, fontSize: 11 }}>
                        {timestamp.date}
                      </div>
                      <div style={{ fontFamily: t.mono, color: t.ink4, fontSize: 10, marginTop: 2 }}>
                        {timestamp.time}
                      </div>
                    </div>
                    <div>
                      <div
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 6,
                          color: stageStyle.color,
                          background: stageStyle.background,
                          border: `1px solid ${stageStyle.border}`,
                          borderRadius: 999,
                          padding: "4px 8px",
                          fontFamily: t.mono,
                          fontSize: 10,
                          fontWeight: 800,
                          textTransform: "uppercase",
                          letterSpacing: 0.4,
                        }}
                      >
                        <span
                          style={{
                            width: 7,
                            height: 7,
                            borderRadius: 4,
                            background: stageStyle.color,
                          }}
                        />
                        {stageStyle.label}
                      </div>
                      <div style={{ marginTop: 7, color: t.ink4, fontFamily: t.mono, fontSize: 10 }}>
                        {item.actor}
                      </div>
                    </div>
                    <div>
                      <div
                        style={{
                          color: stageStyle.color,
                          fontFamily: t.mono,
                          fontSize: 12,
                          fontWeight: 800,
                          letterSpacing: 0.2,
                        }}
                      >
                        {item.title}
                      </div>
                      <div style={{ marginTop: 5, color: t.ink3, fontSize: 13, lineHeight: 1.45 }}>
                        {item.detail}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
