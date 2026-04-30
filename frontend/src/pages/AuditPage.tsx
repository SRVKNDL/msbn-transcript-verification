import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
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
import { DetailHeader } from "../components/DetailHeader";
import { APP_ROUTES, applicationReviewPath } from "../navigation";
import type { DetailBackState } from "../navigation";
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

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function severityColor(severity: Flag["severity"], t: ReturnType<typeof useT>) {
  if (severity === "High") return { tone: t.high, bg: t.highBg };
  if (severity === "Medium") return { tone: t.med, bg: t.medBg };
  return { tone: t.low, bg: t.lowBg };
}

export function AuditPage({ embedded = false }: { embedded?: boolean }) {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const t = useT();
  const user = getCurrentUser();
  const routeState = location.state as DetailBackState | null;
  const reviewRouteState = routeState?.from ? { state: routeState } : undefined;
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [flags, setFlags] = useState<Flag[]>([]);
  const [app, setApp] = useState<Application | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPrinting, setIsPrinting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const printInProgressRef = useRef(false);

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
  const timelineColumns = Math.max(1, timelineItems.length + 1);
  const timelineCardWidth = Math.max(88, Math.min(150, Math.floor(980 / timelineColumns)));
  const timelineHeight = 340;
  const timelineBranchOffset = 72;
  const timelineBranchHeight = 62;
  const legendStages: AuditStage[] = ["created", "processing", "flag", "review", "system"];

  function handleDownloadAuditTrail() {
    if (!app || !id || isPrinting || printInProgressRef.current) return;

    printInProgressRef.current = true;
    setIsPrinting(true);
    setError(null);

    const generatedAt = new Date();
    const summaryCards = [
      ["Application ID", app.applicationId || id],
      ["Applicant", app.applicantName || "Not provided"],
      ["Institution", app.institution || "Not provided"],
      ["Status", formatStatusLabel(app.status || "unknown")],
      ["Flags", String(flags.length)],
      ["Pages", String(app.pageCount || 0)],
      ["Generated", generatedAt.toLocaleString()],
      ["Reviewer", user?.email ?? "Reviewer account"],
    ];

    const eventMarkup = timelineItems
      .map((item) => {
        const stageStyle = auditStageStyle(item.stage, t);
        const timestamp = formatAuditTimestamp(item.ts);
        return `
          <div class="event-row">
            <div class="event-time">
              <div>${escapeHtml(timestamp.date)}</div>
              <div class="muted">${escapeHtml(timestamp.time)}</div>
            </div>
            <div class="event-stage" style="color:${stageStyle.color};background:${stageStyle.background};border-color:${stageStyle.border};">
              ${escapeHtml(stageStyle.label)}
            </div>
            <div class="event-body">
              <div class="event-title" style="color:${stageStyle.color};">${escapeHtml(item.title)}</div>
              <div class="event-meta">${escapeHtml(item.actor)}</div>
              <div class="event-detail">${escapeHtml(item.detail)}</div>
            </div>
          </div>
        `;
      })
      .join("");

    const flagMarkup = flags.length === 0
      ? `<div class="empty-state">No flags were returned for this application.</div>`
      : flags.map((flag, index) => {
        const palette = severityColor(flag.severity, t);
        const snippets = flag.sourceLocation.spans.length > 0
          ? flag.sourceLocation.spans
              .map((span) => `<blockquote>${escapeHtml(span)}</blockquote>`)
              .join("")
          : `<blockquote>No text span was provided for this flag.</blockquote>`;

        return `
          <section class="flag-card">
            <div class="flag-card-head">
              <div>
                <div class="flag-code">${escapeHtml(flag.ruleCode)}</div>
                <div class="flag-name">${escapeHtml(flag.ruleName.replaceAll("_", " ").toLowerCase())}</div>
              </div>
              <div class="flag-badges">
                <span class="severity-chip" style="color:${palette.tone};background:${palette.bg};border-color:${palette.tone};">${escapeHtml(flag.severity)}</span>
                <span class="safe-chip">${escapeHtml(flag.safePractice)}</span>
              </div>
            </div>
            <div class="flag-grid">
              <div>
                <div class="label">Page</div>
                <div class="value">${escapeHtml(String(flag.sourceLocation.page || "Unknown"))}</div>
              </div>
              <div>
                <div class="label">Flag Status</div>
                <div class="value">${escapeHtml(flag.status)}</div>
              </div>
              <div>
                <div class="label">Flag #</div>
                <div class="value">${index + 1} of ${flags.length}</div>
              </div>
            </div>
            <div class="flag-section">
              <div class="label">Rationale</div>
              <div class="body-copy">${escapeHtml(flag.rationale)}</div>
            </div>
            <div class="flag-section">
              <div class="label">Transcript Evidence</div>
              <div class="evidence-list">${snippets}</div>
            </div>
          </section>
        `;
      }).join("");

    const reportHtml = `
      <!doctype html>
      <html lang="en">
        <head>
          <meta charset="utf-8" />
          <title>Audit Trail - ${escapeHtml(app.applicationId || id)}</title>
          <style>
            :root {
              color-scheme: light;
            }
            * { box-sizing: border-box; }
            body {
              margin: 0;
              font-family: "Open Sans", Arial, sans-serif;
              color: #111827;
              background: #f4f7fb;
            }
            .page {
              width: 100%;
              max-width: 1040px;
              margin: 0 auto;
              padding: 28px 28px 36px;
            }
            .report-shell {
              background: #ffffff;
              border: 1px solid #dbe3ef;
              border-top: 5px solid #0d2240;
              border-radius: 8px;
              overflow: hidden;
            }
            .report-header {
              padding: 26px 28px 22px;
              border-bottom: 1px solid #e5e7eb;
              background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
            }
            .eyebrow {
              font-family: "IBM Plex Mono", monospace;
              font-size: 11px;
              letter-spacing: 0.8px;
              text-transform: uppercase;
              color: #6b7280;
            }
            h1 {
              margin: 10px 0 6px;
              font-family: "Montserrat", Arial, sans-serif;
              font-size: 28px;
              line-height: 1.1;
            }
            .subhead {
              font-size: 14px;
              color: #4b5563;
            }
            .summary-grid {
              display: grid;
              grid-template-columns: repeat(4, minmax(0, 1fr));
              gap: 10px;
              padding: 20px 28px;
              background: #f8fafc;
              border-bottom: 1px solid #e5e7eb;
            }
            .summary-card {
              background: #ffffff;
              border: 1px solid #dbe3ef;
              border-radius: 6px;
              padding: 10px 12px;
            }
            .label {
              font-family: "IBM Plex Mono", monospace;
              font-size: 10px;
              letter-spacing: 0.5px;
              text-transform: uppercase;
              color: #6b7280;
              margin-bottom: 5px;
            }
            .value {
              font-size: 13px;
              color: #1f2937;
              font-weight: 600;
              line-height: 1.35;
            }
            .section {
              padding: 22px 28px 8px;
            }
            .section-title {
              font-family: "Montserrat", Arial, sans-serif;
              font-size: 19px;
              margin: 0 0 6px;
            }
            .section-copy {
              font-size: 13px;
              color: #6b7280;
              margin-bottom: 14px;
            }
            .event-row {
              display: grid;
              grid-template-columns: 130px 110px minmax(0, 1fr);
              gap: 14px;
              align-items: start;
              padding: 12px 0;
              border-top: 1px solid #eef2f7;
            }
            .event-row:first-of-type { border-top: none; }
            .event-time,
            .event-meta {
              font-family: "IBM Plex Mono", monospace;
              font-size: 11px;
            }
            .muted {
              color: #9ca3af;
              margin-top: 3px;
            }
            .event-stage,
            .safe-chip,
            .severity-chip {
              display: inline-flex;
              align-items: center;
              justify-content: center;
              border: 1px solid;
              border-radius: 999px;
              padding: 4px 8px;
              font-family: "IBM Plex Mono", monospace;
              font-size: 10px;
              font-weight: 800;
              letter-spacing: 0.4px;
              text-transform: uppercase;
            }
            .event-stage {
              width: fit-content;
            }
            .event-title {
              font-family: "IBM Plex Mono", monospace;
              font-size: 12px;
              font-weight: 800;
              margin-bottom: 5px;
            }
            .event-detail,
            .body-copy {
              font-size: 13px;
              line-height: 1.55;
              color: #374151;
            }
            .flags-layout {
              display: grid;
              gap: 14px;
            }
            .flag-card {
              border: 1px solid #dbe3ef;
              border-left: 5px solid #0d2240;
              border-radius: 8px;
              padding: 16px 18px;
              break-inside: avoid;
              page-break-inside: avoid;
              background: #ffffff;
            }
            .flag-card-head {
              display: flex;
              justify-content: space-between;
              gap: 16px;
              align-items: start;
            }
            .flag-badges {
              display: flex;
              gap: 8px;
              align-items: center;
              flex-wrap: wrap;
            }
            .flag-code {
              font-family: "IBM Plex Mono", monospace;
              font-size: 14px;
              font-weight: 800;
              color: #111827;
            }
            .flag-name {
              margin-top: 5px;
              font-size: 13px;
              color: #4b5563;
              font-weight: 600;
            }
            .safe-chip {
              color: #0d2240;
              background: #eff6ff;
              border-color: #93c5fd;
            }
            .flag-grid {
              display: grid;
              grid-template-columns: repeat(3, minmax(0, 1fr));
              gap: 12px;
              margin-top: 16px;
              padding: 12px;
              border-radius: 6px;
              background: #f8fafc;
              border: 1px solid #e5e7eb;
            }
            .flag-section {
              margin-top: 16px;
            }
            .evidence-list {
              display: grid;
              gap: 8px;
            }
            blockquote {
              margin: 0;
              padding: 10px 12px;
              border-left: 3px solid #0d2240;
              background: #f8fafc;
              color: #1f2937;
              font-size: 13px;
              line-height: 1.55;
            }
            .empty-state {
              padding: 18px;
              border: 1px dashed #cbd5e1;
              border-radius: 8px;
              background: #f8fafc;
              color: #6b7280;
              font-size: 13px;
            }
            @media print {
              body { background: #ffffff; }
              .page { max-width: none; padding: 0; }
              .report-shell { border: none; border-top: none; }
            }
          </style>
        </head>
        <body>
          <div class="page">
            <div class="report-shell">
              <div class="report-header">
                <div class="eyebrow">Mississippi Board of Nursing · Audit Trail</div>
                <h1>${escapeHtml(app.applicantName || "Application Audit Trail")}</h1>
                <div class="subhead">Application #${escapeHtml(app.applicationId || id)} · ${escapeHtml(app.institution || "Institution not provided")}</div>
              </div>
              <div class="summary-grid">
                ${summaryCards
                  .map(([label, value]) => `
                    <div class="summary-card">
                      <div class="label">${escapeHtml(label)}</div>
                      <div class="value">${escapeHtml(value)}</div>
                    </div>
                  `)
                  .join("")}
              </div>
              <section class="section">
                <h2 class="section-title">Audit Events</h2>
                <div class="section-copy">Chronological record of intake, processing, flags, and reviewer activity.</div>
                ${eventMarkup}
              </section>
              <section class="section" style="padding-bottom: 28px;">
                <h2 class="section-title">Flag Evidence</h2>
                <div class="section-copy">Each flag includes its rationale, page reference, and the transcript excerpt returned by the review API.</div>
                <div class="flags-layout">${flagMarkup}</div>
              </section>
            </div>
          </div>
        </body>
      </html>
    `;

    const iframe = document.createElement("iframe");
    iframe.setAttribute("aria-hidden", "true");
    iframe.style.position = "fixed";
    iframe.style.right = "0";
    iframe.style.bottom = "0";
    iframe.style.width = "0";
    iframe.style.height = "0";
    iframe.style.border = "0";
    iframe.style.opacity = "0";
    iframe.style.pointerEvents = "none";

    let cleanedUp = false;
    let printStarted = false;
    let fallbackTimer: number | undefined;
    const cleanup = () => {
      if (cleanedUp) return;
      cleanedUp = true;
      if (fallbackTimer !== undefined) {
        window.clearTimeout(fallbackTimer);
      }
      window.setTimeout(() => {
        iframe.remove();
        printInProgressRef.current = false;
        setIsPrinting(false);
      }, 200);
    };

    iframe.onload = () => {
      if (printStarted) return;
      printStarted = true;

      const printFrame = iframe.contentWindow;
      if (!printFrame) {
        setError("Unable to prepare audit trail for printing.");
        cleanup();
        return;
      }

      printFrame.onafterprint = cleanup;
      printFrame.focus();
      window.setTimeout(() => {
        printFrame.print();
      }, 200);
      fallbackTimer = window.setTimeout(cleanup, 60_000);
    };

    document.body.appendChild(iframe);
    iframe.srcdoc = reportHtml;
  }

  return (
    <div
      style={{
        width: embedded ? "100%" : "100vw",
        height: embedded ? "100%" : "100vh",
        background: t.bg,
        color: t.ink,
        fontFamily: t.sans,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {!embedded && <header
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
          onClick={() => navigate(APP_ROUTES.audit)}
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
            background: "#2A73EC",
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
          onClick={() => navigate(APP_ROUTES.dashboard)}
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
      </header>}

      <main style={{ flex: 1, overflow: "auto", padding: "24px 34px 44px" }}>
        <DetailHeader
          backLabel="Audit Log"
          backTo="/audit"
          eyebrow="SP-9 Compliance Trail"
          title={app?.applicantName ?? "Application"}
          subtitle={`#${id}${app?.institution ? ` · ${app.institution}` : ""}`}
          style={{
            maxWidth: 1180,
            margin: "0 auto 16px",
            border: `1px solid ${t.line}`,
            borderRadius: 6,
          }}
          statusSummary={
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
          }
          secondaryActions={
            <button
              onClick={handleDownloadAuditTrail}
              disabled={isLoading || !app || isPrinting}
              title="Download audit trail"
              aria-label="Download audit trail"
              style={{
                width: 34,
                height: 34,
                borderRadius: 5,
                border: `1px solid ${t.line}`,
                background: t.surfaceAlt,
                color: isLoading || !app || isPrinting ? t.ink4 : t.ink2,
                cursor: isLoading || !app || isPrinting ? "not-allowed" : "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                padding: 0,
                boxShadow: "0 6px 16px rgba(15, 23, 42, 0.06)",
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path
                  d="M7 8V4H17V8M7 14H17V20H7V14ZM5 8H19C20.1046 8 21 8.89543 21 10V15H17V12H7V15H3V10C3 8.89543 3.89543 8 5 8Z"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          }
        />

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
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
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
          </div>

          {error ? (
            <div style={{ padding: 20, color: t.high, fontSize: 13 }}>{error}</div>
          ) : isLoading ? (
            <div style={{ padding: 20, color: t.ink3, fontSize: 13 }}>
              Loading audit timeline...
            </div>
          ) : (
            <div style={{ padding: "24px 18px 10px" }}>
              <div
                style={{
                  position: "relative",
                  width: "100%",
                  height: timelineHeight,
                  display: "grid",
                  gridTemplateColumns: `repeat(${timelineColumns}, minmax(0, 1fr))`,
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
                  const opensReview = item.stage === "flag";

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
                          top: isAbove
                            ? `calc(50% - ${timelineBranchOffset}px)`
                            : "calc(50% + 10px)",
                          height: timelineBranchHeight,
                          borderLeft: `2px solid ${stageStyle.color}`,
                          opacity: 0.65,
                        }}
                      />
                      <div
                        onClick={() => {
                          if (opensReview && id) navigate(applicationReviewPath(id), reviewRouteState);
                        }}
                        title={opensReview ? "Open review page" : undefined}
                        style={{
                          position: "absolute",
                          left: "50%",
                          top: isAbove ? 0 : `calc(50% + ${timelineBranchOffset}px)`,
                          transform: "translateX(-50%)",
                          width: timelineCardWidth,
                          minHeight: 70,
                          background: stageStyle.background,
                          border: `1px solid ${stageStyle.border}`,
                          borderRadius: 6,
                          padding: "9px 10px",
                          boxShadow: "0 10px 22px rgba(15, 23, 42, 0.08)",
                          cursor: opensReview ? "pointer" : "default",
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
                      top: `calc(50% - ${timelineBranchOffset}px)`,
                      height: timelineBranchHeight,
                      borderLeft: reviewed
                        ? `2px solid ${terminalStyle.color}`
                        : `2px dashed ${t.ink4}`,
                      opacity: 0.75,
                    }}
                  />
                  <div
                    onClick={() => {
                      if (id) navigate(applicationReviewPath(id), reviewRouteState);
                    }}
                    title="Open review page"
                    style={{
                      position: "absolute",
                      left: "50%",
                      top: 0,
                      transform: "translateX(-50%)",
                      width: timelineCardWidth,
                      minHeight: 70,
                      background: terminalStyle.background,
                      border: `1px solid ${terminalStyle.border}`,
                      borderRadius: 6,
                      padding: "9px 10px",
                      boxShadow: "0 10px 22px rgba(15, 23, 42, 0.08)",
                      cursor: "pointer",
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
              onClick={() => id && navigate(applicationReviewPath(id), reviewRouteState)}
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
