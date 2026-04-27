import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import type { WheelEvent } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { useT } from "../theme";
import { useViewport } from "../useViewport";
import { SeverityChip } from "../components/SeverityChip";
import { ConfidenceDot } from "../components/ConfidenceDot";
import { ProgressBar } from "../components/ProgressBar";
import { ActionButton } from "../components/ActionButton";
import { DetailHeader } from "../components/DetailHeader";
import {
  APP_ROUTES,
  applicationReviewPath,
  applicationReviewedPath,
  detailBackStateFor,
  hasApplicationSummary,
} from "../navigation";
import type { DetailBackState } from "../navigation";
import { getApplication, getPageImage, listApplications, submitDecision } from "../api";
import { getCurrentUser } from "../auth";
import type { Application, Flag, Decisions, OverallDecision, ExtractionData, ExtractionRow } from "../types";

const DEFAULT_TRANSCRIPT_ZOOM = 2;
const SEVERITY_ORDER = { High: 0, Medium: 1, Low: 2 } as const;
type QueueSort = "oldest" | "newest" | "flags" | "severity" | "applicant" | "institution";
const QUEUE_SORT_LABELS: Record<QueueSort, string> = {
  oldest: "oldest first",
  newest: "newest first",
  flags: "most flags",
  severity: "severity",
  applicant: "applicant",
  institution: "institution",
};
type FlagSort = "severity" | "page" | "rule" | "status";

function severityRank(severity: Flag["severity"]) {
  return SEVERITY_ORDER[severity] ?? 3;
}

function appSeverityRank(severity: Application["highestSeverity"]) {
  if (severity === "High") return 0;
  if (severity === "Medium") return 1;
  if (severity === "Low") return 2;
  return 3;
}

// --- Toast notification ---
function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  const t = useT();

  useEffect(() => {
    const timeoutId = setTimeout(onClose, 3500);
    return () => clearTimeout(timeoutId);
  }, [onClose]);

  return (
    <div style={{
      position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)",
      background: t.primary, color: t.primaryInk, padding: "12px 24px",
      borderRadius: 4, fontSize: 13, fontWeight: 500, zIndex: 100,
      boxShadow: "0 8px 24px rgba(0,0,0,0.3)",
      fontFamily: "'Open Sans', system-ui, sans-serif",
      animation: "toastIn 300ms cubic-bezier(.2,.7,.3,1)",
    }}>
      <span style={{ marginRight: 8, color: t.ok }}>&#10003;</span>
      {message}
    </div>
  );
}

// --- Keyboard shortcut legend ---
function ShortcutLegend({ onClose }: { onClose: () => void }) {
  const t = useT();
  const shortcuts = [
    ["J / K", "Next / previous flag"],
    ["C", "Confirm current flag"],
    ["O", "Override current flag"],
    ["1\u20139", "Jump to page"],
    ["B", "Toggle review queue"],
    ["F", "Toggle transcript fullscreen"],
    ["?", "Toggle this legend"],
    ["Esc", "Close overlay"],
  ];
  return (
    <div style={{
      position: "absolute", inset: 0, background: "rgba(12,18,28,0.5)",
      zIndex: 50, display: "flex", alignItems: "center", justifyContent: "center",
    }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} style={{
        background: t.surface, borderRadius: 4, padding: "24px 32px",
        boxShadow: "0 20px 60px rgba(0,0,0,0.3)", minWidth: 280,
        border: `1px solid ${t.line}`,
      }}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 14, color: t.ink }}>Keyboard shortcuts</div>
        {shortcuts.map(([key, desc]) => (
          <div key={key} style={{ display: "flex", gap: 14, alignItems: "center", marginBottom: 8 }}>
            <span style={{
              fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
              fontSize: 11, fontWeight: 600, background: t.surfaceAlt,
              border: `1px solid ${t.line}`, borderRadius: 2,
              padding: "2px 8px", minWidth: 40, textAlign: "center", color: t.ink2,
            }}>{key}</span>
            <span style={{ fontSize: 12, color: t.ink2 }}>{desc}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SubmitDecisionModal({
  overallDecision,
  onSelect,
  onClose,
  onSubmit,
  isSubmitting,
}: {
  overallDecision: OverallDecision;
  onSelect: (decision: OverallDecision) => void;
  onClose: () => void;
  onSubmit: () => void;
  isSubmitting: boolean;
}) {
  const t = useT();
  const options: Array<{ value: Exclude<OverallDecision, null>; label: string; tone: string; bg: string }> = [
    { value: "READY_FOR_LICENSING_REVIEW", label: "Ready for licensing review", tone: t.ok, bg: t.okBg },
    { value: "RETURN_TO_APPLICANT", label: "Return to applicant", tone: t.med, bg: t.medBg },
    { value: "DEFERRED", label: "Deferred", tone: t.low, bg: t.lowBg },
    { value: "DENIED", label: "Denied", tone: t.high, bg: t.highBg },
  ];

  return (
    <div
      onClick={onClose}
      style={{
        position: "absolute",
        inset: 0,
        background: "rgba(12,18,28,0.42)",
        zIndex: 80,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(520px, 100%)",
          background: t.surface,
          border: `1px solid ${t.line}`,
          borderTop: `3px solid ${t.accent}`,
          borderRadius: 4,
          boxShadow: "0 24px 60px rgba(0,0,0,0.24)",
          overflow: "hidden",
        }}
      >
        <div style={{ padding: "18px 22px 14px", borderBottom: `1px solid ${t.line2}` }}>
          <div style={{ fontSize: 10, color: t.ink4, fontFamily: t.mono, letterSpacing: 0.6, textTransform: "uppercase", marginBottom: 6 }}>
            Final decision
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, fontFamily: t.serif, color: t.ink }}>Submit review outcome</div>
        </div>
        <div style={{ padding: 18, display: "grid", gap: 10 }}>
          {options.map((option) => {
            const active = overallDecision === option.value;
            return (
              <button
                key={option.value}
                onClick={() => onSelect(option.value)}
                style={{
                  width: "100%",
                  border: `1px solid ${active ? option.tone : t.line}`,
                  background: active ? option.bg : t.surface,
                  color: active ? option.tone : t.ink2,
                  borderRadius: 4,
                  padding: "12px 14px",
                  cursor: "pointer",
                  fontFamily: "inherit",
                  fontSize: 13,
                  fontWeight: active ? 700 : 600,
                  textAlign: "left",
                }}
              >
                {option.label}
              </button>
            );
          })}
        </div>
        <div style={{ padding: "0 18px 18px", display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <button
            onClick={onClose}
            style={{
              border: `1px solid ${t.line}`,
              background: t.surface,
              color: t.ink2,
              borderRadius: 3,
              padding: "9px 12px",
              cursor: "pointer",
              fontFamily: "inherit",
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            Cancel
          </button>
          <button
            onClick={onSubmit}
            disabled={!overallDecision || isSubmitting}
            style={{
              border: "none",
              background: overallDecision && !isSubmitting ? t.accent : t.line,
              color: overallDecision && !isSubmitting ? "#fff" : t.ink4,
              borderRadius: 3,
              padding: "9px 14px",
              cursor: overallDecision && !isSubmitting ? "pointer" : "not-allowed",
              fontFamily: "inherit",
              fontSize: 12,
              fontWeight: 700,
            }}
          >
            {isSubmitting ? "Submitting..." : "Confirm submission"}
          </button>
        </div>
      </div>
    </div>
  );
}

function timeAgo(hrs: number) {
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function Stat({ label, value }: { label: string; value: string }) {
  const t = useT();
  return (
    <div>
      <div style={{ fontSize: 10, color: t.ink4, fontFamily: t.mono, letterSpacing: 0.4, textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: 14, color: t.ink, fontWeight: 600, fontFamily: t.mono }}>{value}</div>
    </div>
  );
}

function hasExtractedSummary(app: Application) {
  return hasApplicationSummary(app);
}

function ReviewStateScreen({
  title,
  message,
  onBack,
  embedded = false,
}: {
  title: string;
  message: string;
  onBack: () => void;
  embedded?: boolean;
}) {
  const t = useT();

  return (
    <div style={{
      width: embedded ? "100%" : "100vw",
      height: embedded ? "100%" : "100vh",
      background: t.bg,
      color: t.ink,
      fontFamily: "'Open Sans', system-ui, sans-serif",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: 24,
      boxSizing: "border-box",
    }}>
      <div style={{
        width: "min(520px, 100%)",
        background: t.surface,
        border: `1px solid ${t.line}`,
        borderTop: `3px solid ${t.accent}`,
        borderRadius: 3,
        padding: "24px 28px",
        boxShadow: "0 18px 45px rgba(0,0,0,0.16)",
      }}>
        <div style={{
          fontSize: 11,
          color: t.ink4,
          fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
          letterSpacing: 0.6,
          textTransform: "uppercase",
          marginBottom: 8,
        }}>
          Review detail
        </div>
        <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 10, fontFamily: "'Montserrat', system-ui, sans-serif", color: t.ink }}>
          {title}
        </div>
        <div style={{ fontSize: 13, color: t.ink2, lineHeight: 1.6, marginBottom: 18 }}>
          {message}
        </div>
        <button onClick={onBack} style={{
          border: "none",
          background: t.primary,
          color: t.primaryInk,
          padding: "9px 14px",
          fontSize: 12,
          fontWeight: 600,
          borderRadius: 2,
          cursor: "pointer",
          fontFamily: "inherit",
        }}>
          Back to review queue
        </button>
      </div>
    </div>
  );
}

// --- TranscriptPageViewer: fetches S3 presigned URLs for page images ---
function TranscriptPageViewer({
  appId,
  page,
  flags,
  pdfScale,
}: {
  appId: string;
  page: number;
  flags: Flag[];
  pdfScale: number;
}) {
  const t = useT();
  const [imgUrl, setImgUrl] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "loaded" | "error">("idle");

  useEffect(() => {
    setImgUrl(null);
    setStatus("loading");
    let cancelled = false;
    getPageImage(appId, page)
      .then((data) => {
        if (cancelled) return;
        if (data?.url) { setImgUrl(data.url); setStatus("loaded"); }
        else setStatus("error");
      })
      .catch(() => { if (!cancelled) setStatus("error"); });
    return () => { cancelled = true; };
  }, [appId, page]);

  if (status === "loading") return (
    <div style={{
      width: Math.round(560 * pdfScale), minHeight: Math.round(720 * pdfScale),
      background: t.surface,
      border: `1px solid ${t.line}`, borderRadius: 2,
      boxShadow: "0 8px 24px rgba(0,0,0,0.16)",
      display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 16,
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: "50%",
        border: `3px solid ${t.line}`, borderTopColor: t.accent,
        animation: "txSpin 0.8s linear infinite",
      }} />
      <div style={{ fontSize: 12, color: t.ink4, fontFamily: t.mono }}>
        Fetching page {page} from S3…
      </div>
      <style>{`@keyframes txSpin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );

  if (status === "loaded" && imgUrl) return (
    <div style={{
      width: Math.round(560 * pdfScale), background: t.surface,
      border: `1px solid ${t.line}`, borderRadius: 2,
      boxShadow: "0 8px 24px rgba(0,0,0,0.16)",
      position: "relative", overflow: "hidden",
    }}>
      <img
        src={imgUrl}
        alt={`Transcript page ${page}`}
        style={{ width: "100%", display: "block" }}
        onError={() => setStatus("error")}
      />
      {flags.filter(f => f.sourceLocation.page === page).map(f => (
        <div key={f.ruleCode} style={{
          position: "absolute", bottom: 12, left: 12,
          background: f.severity === "High" ? t.highBg : f.severity === "Medium" ? t.medBg : t.lowBg,
          border: `1px solid ${f.severity === "High" ? t.high : f.severity === "Medium" ? t.med : t.low}`,
          borderRadius: 4, padding: "4px 10px",
          fontSize: 10, fontFamily: t.mono,
          color: f.severity === "High" ? t.high : f.severity === "Medium" ? t.med : t.low,
          fontWeight: 600,
        }}>&#9873; {f.ruleCode} · {f.severity}</div>
      ))}
    </div>
  );

  return (
    <div style={{
      width: Math.round(560 * pdfScale), minHeight: Math.round(720 * pdfScale),
      background: t.surface,
      border: `1px solid ${t.line}`,
      boxShadow: "0 8px 24px rgba(0,0,0,0.16)",
      padding: "36px 42px", boxSizing: "border-box",
      display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      textAlign: "center", color: t.ink3,
    }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: t.ink, fontFamily: t.serif, marginBottom: 8 }}>
        Transcript page unavailable
      </div>
      <div style={{ fontSize: 12, lineHeight: 1.6, maxWidth: 380 }}>
        Page {page} could not be loaded from the transcript page-image API. Confirm that
        GET /applications/{`{id}`}/pages/{`{page}`} returns a presigned image URL for this application.
      </div>
    </div>
  );
}

// --- Queue row (sidebar) ---
function QueueRow({ app, active, onClick, shaded }: { app: Application; active: boolean; onClick: () => void; shaded?: boolean }) {
  const t = useT();
  const dotColor = app.highestSeverity === "High" ? t.high
    : app.highestSeverity === "Medium" ? t.med
    : app.highestSeverity === "Low" ? t.low
    : t.ink4;
  const rowBackground = active ? t.accentBg : shaded ? t.surfaceAlt : t.surface;
  const rowBorder = active ? t.accent : shaded ? t.line : "transparent";
  const metaText = [app.country, app.programYear].filter(Boolean).join(" · ") || timeAgo(app.ageHours);

  return (
    <div onClick={onClick} style={{
      display: "grid",
      gridTemplateColumns: "14px minmax(0, 1fr)",
      gap: 10,
      alignItems: "start",
      padding: "9px 10px",
      margin: "0 10px 6px",
      borderRadius: 6,
      border: `1px solid ${rowBorder}`,
      background: rowBackground,
      cursor: "pointer",
      fontSize: 13,
      color: active ? t.ink : t.ink2,
      boxShadow: active ? "0 8px 18px rgba(0,94,162,0.11)" : "none",
      minHeight: 86,
      boxSizing: "border-box",
    }}>
      <div style={{ width: 6, height: 6, borderRadius: 3, background: dotColor, marginTop: 7 }} />
      <div style={{ minWidth: 0, display: "grid", gridTemplateRows: "20px 16px 16px", alignContent: "start" }}>
        <div style={{
          fontWeight: active ? 600 : 500,
          color: active ? t.ink : t.ink2,
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}>
          {app.applicantName || app.originalFilename || "Transcript upload"}
        </div>
        <div style={{
          fontSize: 11,
          color: t.ink4,
          fontFamily: t.mono,
          marginTop: 2,
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}>
          {app.applicationId}
        </div>
        <div style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) auto",
          gap: 6,
          alignItems: "center",
          marginTop: 3,
          fontSize: 10,
          color: t.ink3,
          fontFamily: t.mono,
          minHeight: 16,
        }}>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {metaText}
          </span>
          <span style={{ flexShrink: 0 }}>
            {app.flagCount} flag{app.flagCount !== 1 ? "s" : ""}
          </span>
        </div>
      </div>
    </div>
  );
}

// --- Flag card ---
function FlagCard({ flag, decision, notes, onDecision, onNotes, onJumpTo, onOpenData, active, onClick, shaded }: {
  flag: Flag; decision?: string; notes?: string;
  onDecision: (d: "CONFIRM" | "OVERRIDE") => void; onNotes: (n: string) => void;
  onJumpTo: () => void; onOpenData: () => void;
  active: boolean; onClick: () => void; shaded?: boolean;
}) {
  const t = useT();
  const resolved = !!decision;
  const cardBackground = resolved ? t.surfaceAlt : shaded ? t.surfaceAlt : t.surface;
  return (
    <div onClick={onClick} style={{
      border: `1px solid ${active ? t.accent : t.line}`,
      borderLeft: `3px solid ${flag.severity === "High" ? t.high : flag.severity === "Medium" ? t.med : t.low}`,
      background: cardBackground,
      opacity: resolved && !active ? 0.72 : 1,
      borderRadius: 2, padding: "12px 14px", cursor: "pointer", marginBottom: 8,
      transition: "background 140ms, opacity 140ms",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
        <span style={{ fontFamily: t.mono, fontSize: 12, fontWeight: 600, color: t.ink }}>{flag.ruleCode}</span>
        <SeverityChip severity={flag.severity} />
        {resolved && (
          <span style={{
            fontFamily: t.mono, fontSize: 10, fontWeight: 600,
            color: decision === "CONFIRM" ? t.high : t.ok,
            background: decision === "CONFIRM" ? t.highBg : t.okBg,
            padding: "2px 7px", borderRadius: 2, letterSpacing: 0.3,
          }}>
            {decision === "CONFIRM" ? "\u2713 CONFIRMED" : "\u2713 OVERRIDDEN"}
          </span>
        )}
        <span style={{ fontSize: 10, color: t.ink4, fontFamily: t.mono, marginLeft: "auto" }}>
          {flag.safePractice}
        </span>
      </div>
      <div style={{ fontSize: 12, color: t.ink2, fontWeight: 500, marginBottom: 4 }}>
        {flag.ruleName.replaceAll("_", " ").toLowerCase()}
      </div>
      <div style={{ fontSize: 12, color: t.ink3, lineHeight: 1.55, marginBottom: 10 }}>
        {flag.rationale}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: t.ink4, flexWrap: "wrap" }}>
        <button onClick={(e) => { e.stopPropagation(); onJumpTo(); }} style={{
          border: `1px solid ${t.line}`, background: t.surface,
          fontSize: 10, padding: "3px 8px", borderRadius: 2, cursor: "pointer",
          fontFamily: t.mono, color: t.ink2,
        }}>
          &darr; page {flag.sourceLocation.page}
        </button>
        <button onClick={(e) => { e.stopPropagation(); onOpenData(); }} style={{
          border: `1px solid ${t.line}`, background: t.surface,
          fontSize: 10, padding: "3px 8px", borderRadius: 2, cursor: "pointer",
          fontFamily: t.mono, color: t.ink2,
        }}>
          # data
        </button>
        <span style={{ fontSize: 10, fontFamily: t.mono }}>
          "{flag.sourceLocation.spans[0]}"
        </span>
      </div>

      {active && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px dashed ${t.line}` }}>
          <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
            <ActionButton active={decision === "CONFIRM"} onClick={(e) => { e.stopPropagation(); onDecision("CONFIRM"); }} variant="confirm">Confirm flag</ActionButton>
            <ActionButton active={decision === "OVERRIDE"} onClick={(e) => { e.stopPropagation(); onDecision("OVERRIDE"); }} variant="override">Override</ActionButton>
          </div>
          {decision === "OVERRIDE" && (
            <textarea value={notes || ""} onChange={(e) => onNotes(e.target.value)}
              onClick={(e) => e.stopPropagation()}
              placeholder="Notes required when overriding a flag..."
              style={{
                width: "100%", minHeight: 60, boxSizing: "border-box",
                border: `1px solid ${t.line}`, borderRadius: 2,
                padding: 8, fontSize: 12, fontFamily: "inherit", color: t.ink2,
                background: t.surface, resize: "vertical",
              }} />
          )}
        </div>
      )}
    </div>
  );
}

// --- Extracted data drawer ---
function ExtractedDataDrawer({ flag, extraction, onClose }: {
  flag: Flag | null; extraction: ExtractionData; onClose: () => void;
}) {
  const t = useT();
  const [tab, setTab] = useState<"physical" | "content" | "program">("physical");
  const fieldMap: Record<string, string[]> = {
    CONT_005: ["gpa_arithmetic_consistency"],
    PHYS_004: ["text_alignment"],
    PROG_002: ["graduation_confirmation_present"],
  };
  const highlighted = flag ? (fieldMap[flag.ruleCode] ?? []) : [];
  const totalFields = extraction.physical.length + extraction.content.length + extraction.program.length;

  const TABS = [
    { key: "physical" as const, label: "Physical", count: extraction.physical.length },
    { key: "content" as const, label: "Content", count: extraction.content.length },
    { key: "program" as const, label: "Program", count: extraction.program.length },
  ];
  const rows = extraction[tab];

  return (
    <div style={{
      position: "absolute", inset: 0, background: "rgba(12,18,28,0.4)",
      zIndex: 30, display: "flex", justifyContent: "flex-end",
    }}>
      <div onClick={onClose} style={{ flex: 1 }} />
      <div style={{
        width: "min(500px, 100vw)", background: t.surface, height: "100%",
        borderLeft: `1px solid ${t.line}`, display: "flex", flexDirection: "column",
        boxShadow: "-20px 0 50px rgba(0,0,0,0.18)",
        animation: "drawerSlide 220ms cubic-bezier(.2,.7,.3,1)",
      }}>
        <div style={{ padding: "18px 22px 12px", borderBottom: `1px solid ${t.line}` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <span style={{ fontSize: 10, fontFamily: t.mono, color: t.ink4, letterSpacing: 0.5, textTransform: "uppercase" }}>Extracted fields</span>
            <div style={{ flex: 1 }} />
            <button onClick={onClose} style={{
              border: "none", background: "transparent", cursor: "pointer",
              color: t.ink3, fontSize: 16, padding: 0, lineHeight: 1,
            }}>&times;</button>
          </div>
          <div style={{ fontSize: 16, fontWeight: 600, color: t.ink, marginBottom: 4, fontFamily: t.serif }}>Bedrock Nova extraction</div>
          <div style={{ fontSize: 11, color: t.ink4, fontFamily: t.mono }}>
            nova-pro-v1:0 · prompt v4.0 · extracted 2026-04-19 14:24 UTC
          </div>
          {flag && (
            <div style={{
              marginTop: 12, padding: "7px 10px",
              background: t.highBg, border: `1px solid ${t.high}`,
              borderRadius: 2, fontSize: 11, color: t.ink2,
              fontFamily: t.mono,
            }}>
              showing fields related to <b style={{ color: t.high }}>{flag.ruleCode}</b>
            </div>
          )}
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: 0, borderBottom: `1px solid ${t.line}`, padding: "0 22px" }}>
          {TABS.map((tabOption) => (
            <button key={tabOption.key} onClick={() => setTab(tabOption.key)} style={{
              border: "none", background: "transparent", cursor: "pointer",
              padding: "10px 14px 10px 0", marginRight: 18,
              fontSize: 12, fontWeight: tab === tabOption.key ? 600 : 400,
              color: tab === tabOption.key ? t.ink : t.ink3,
              borderBottom: `2px solid ${tab === tabOption.key ? t.accent : "transparent"}`,
              marginBottom: -1, fontFamily: "inherit",
            }}>
              {tabOption.label} <span style={{ color: t.ink4, fontFamily: t.mono, fontSize: 11 }}>{tabOption.count}</span>
            </button>
          ))}
        </div>

        {/* Rows */}
        <div style={{ flex: 1, overflow: "auto", padding: "6px 0" }}>
          {rows.map((row, i) => {
            const hi = highlighted.includes(row.field);
            return (
              <div key={i} style={{
                display: "grid", gridTemplateColumns: "1fr 1fr auto",
                gap: 12, alignItems: "baseline", padding: "9px 22px",
                background: hi ? t.highBg : "transparent",
                borderLeft: hi ? `3px solid ${t.high}` : "3px solid transparent",
                borderBottom: `1px solid ${t.line2}`,
              }}>
                <div style={{
                  fontFamily: t.mono,
                  fontSize: 11, color: hi ? t.ink : t.ink3, fontWeight: hi ? 600 : 400,
                }}>{row.field}</div>
                <div style={{ fontSize: 12, color: t.ink2, fontFamily: t.mono }}>{row.value}</div>
                <ConfidenceDot level={row.confidence} />
              </div>
            );
          })}
        </div>

        <div style={{ padding: "12px 22px", borderTop: `1px solid ${t.line}`, fontSize: 10, color: t.ink4, fontFamily: t.mono }}>
          {totalFields} fields · GET /applications/{"{id}"}/extraction
        </div>
      </div>
    </div>
  );
}

function buildFallbackExtraction(app: Application): ExtractionData {
  const row = (field: string, value: string, confidence: "high" | "medium" | "low" = "medium"): ExtractionRow => ({
    field,
    value: value || "Not available",
    confidence: value ? confidence : "low",
  });
  return {
    physical: [
      row("page_count", String(app.pageCount), "high"),
      row("original_filename", app.originalFilename, "high"),
    ],
    content: [
      row("applicant_name", app.applicantName, "high"),
      row("institution", app.institution, "high"),
      row("country", app.country, "medium"),
      row("license_number", app.licenseNumber, "medium"),
      row("application_id", app.applicationId, "high"),
    ],
    program: [
      row("program_year", app.programYear, "medium"),
      row("status", app.status, "high"),
      row("submitted_at", app.submittedAt ? new Date(app.submittedAt).toLocaleString() : "", "high"),
      row("highest_severity", app.highestSeverity ?? "", "high"),
      row("flag_count", String(app.flagCount), "high"),
    ],
  };
}

// --- Main review page ---
export function ReviewPage({ embedded = false }: { embedded?: boolean }) {
  const t = useT();
  const { isPhone, isTablet, isNarrow } = useViewport();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const user = getCurrentUser();
  const routeState = location.state as DetailBackState | null;
  const reviewedBackState = routeState?.from
    ? { state: routeState }
    : detailBackStateFor("queue");

  const [app, setApp] = useState<Application | null>(null);
  const [isAppLoading, setIsAppLoading] = useState(true);
  const [queueApps, setQueueApps] = useState<Application[]>([]);
  const [flags, setFlags] = useState<Flag[]>([]);
  const [extraction, setExtraction] = useState<ExtractionData>({ physical: [], content: [], program: [] });
  const [error, setError] = useState<string | null>(null);
  const [activeFlagIdx, setActiveFlagIdx] = useState(0);
  const [decisions, setDecisions] = useState<Decisions>({});
  const [currentPage, setCurrentPage] = useState(1);
  const [overallDecision, setOverallDecision] = useState<OverallDecision>(null);
  const [flagSort, setFlagSort] = useState<FlagSort>("severity");
  const [submitModalOpen, setSubmitModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [drawerFlag, setDrawerFlag] = useState<Flag | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [queueOpen, setQueueOpen] = useState(true);
  const [queueSort, setQueueSort] = useState<QueueSort>("oldest");
  const [isTranscriptFullscreen, setIsTranscriptFullscreen] = useState(false);
  const [transcriptZoom, setTranscriptZoom] = useState(DEFAULT_TRANSCRIPT_ZOOM);
  const transcriptPaneRef = useRef<HTMLDivElement>(null);
  const transcriptScrollRef = useRef<HTMLDivElement>(null);
  const transcriptZoomRef = useRef(DEFAULT_TRANSCRIPT_ZOOM);

  const pageCount = Math.max(1, app?.pageCount || 1);
  const pages = Array.from({ length: pageCount }, (_, i) => i + 1);
  const totalFields = extraction.physical.length + extraction.content.length + extraction.program.length;
  const groupedFlags = useMemo(() => {
    const indexed = flags
      .map((flag, originalIndex) => ({ flag, originalIndex }))
      .sort((a, b) => a.originalIndex - b.originalIndex);

    return indexed.reduce<Array<{
      ruleCode: string;
      items: Array<{ flag: Flag; originalIndex: number }>;
      groupIndex: number;
      highestSeverity: Flag["severity"];
      firstPage: number;
    }>>((groups, item) => {
      const lastGroup = groups[groups.length - 1];
      if (lastGroup && lastGroup.ruleCode === item.flag.ruleCode) {
        lastGroup.items.push(item);
        if (severityRank(item.flag.severity) < severityRank(lastGroup.highestSeverity)) {
          lastGroup.highestSeverity = item.flag.severity;
        }
        lastGroup.firstPage = Math.min(lastGroup.firstPage, item.flag.sourceLocation.page);
        return groups;
      }

      groups.push({
        ruleCode: item.flag.ruleCode,
        items: [item],
        groupIndex: groups.length,
        highestSeverity: item.flag.severity,
        firstPage: item.flag.sourceLocation.page,
      });
      return groups;
    }, []);
  }, [flags]);
  const sortedFlagGroups = useMemo(() => {
    const groups = [...groupedFlags];
    groups.sort((a, b) => {
      if (flagSort === "status") {
        const aResolved = a.items.every(({ flag }) => decisions[flag.ruleCode]?.decision);
        const bResolved = b.items.every(({ flag }) => decisions[flag.ruleCode]?.decision);
        return Number(aResolved) - Number(bResolved)
          || severityRank(a.highestSeverity) - severityRank(b.highestSeverity)
          || a.firstPage - b.firstPage
          || a.ruleCode.localeCompare(b.ruleCode);
      }
      if (flagSort === "page") {
        return a.firstPage - b.firstPage || a.ruleCode.localeCompare(b.ruleCode);
      }
      if (flagSort === "rule") {
        return a.ruleCode.localeCompare(b.ruleCode) || a.firstPage - b.firstPage;
      }
      return severityRank(a.highestSeverity) - severityRank(b.highestSeverity)
        || a.firstPage - b.firstPage
        || a.ruleCode.localeCompare(b.ruleCode);
    });
    return groups.map((group, index) => ({ ...group, groupIndex: index }));
  }, [decisions, groupedFlags, flagSort]);
  const displayFlags = useMemo(
    () => sortedFlagGroups.flatMap((group) =>
      [...group.items].sort((a, b) =>
        severityRank(a.flag.severity) - severityRank(b.flag.severity)
        || a.flag.sourceLocation.page - b.flag.sourceLocation.page
        || a.originalIndex - b.originalIndex
      )
    ),
    [sortedFlagGroups]
  );

  useEffect(() => {
    transcriptZoomRef.current = transcriptZoom;
  }, [transcriptZoom]);

  const applyTranscriptZoom = useCallback((nextZoom: number, pointerX?: number, pointerY?: number) => {
    const viewport = transcriptScrollRef.current;
    if (!viewport) return;

    const previousZoom = transcriptZoomRef.current;
    const clampedZoom = Math.min(3, Math.max(0.75, nextZoom));

    if (Math.abs(clampedZoom - previousZoom) < 0.001) return;

    const anchorX = pointerX ?? viewport.clientWidth / 2;
    const anchorY = pointerY ?? viewport.clientHeight / 2;
    const contentX = (viewport.scrollLeft + anchorX) / previousZoom;
    const contentY = (viewport.scrollTop + anchorY) / previousZoom;

    transcriptZoomRef.current = clampedZoom;
    setTranscriptZoom(clampedZoom);

    window.requestAnimationFrame(() => {
      viewport.scrollLeft = contentX * clampedZoom - anchorX;
      viewport.scrollTop = contentY * clampedZoom - anchorY;
    });
  }, []);

  const handleTranscriptWheel = useCallback((e: WheelEvent<HTMLDivElement>) => {
    if (!e.ctrlKey && !e.metaKey) return;

    e.preventDefault();

    const viewport = transcriptScrollRef.current;
    if (!viewport) return;

    const rect = viewport.getBoundingClientRect();
    applyTranscriptZoom(
      transcriptZoomRef.current * Math.exp(-e.deltaY * 0.01),
      e.clientX - rect.left,
      e.clientY - rect.top
    );
  }, [applyTranscriptZoom]);

  const zoomTranscriptBy = useCallback((delta: number) => {
    applyTranscriptZoom(transcriptZoomRef.current + delta);
  }, [applyTranscriptZoom]);

  const toggleTranscriptFullscreen = useCallback(() => {
    const pane = transcriptPaneRef.current;
    if (!pane) return;
    if (document.fullscreenElement === pane) {
      void document.exitFullscreen();
      return;
    }
    void pane.requestFullscreen();
  }, []);

  useEffect(() => {
    const onFullscreenChange = () => {
      setIsTranscriptFullscreen(document.fullscreenElement === transcriptPaneRef.current);
    };
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, []);

  // Keyboard shortcuts
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if ((e.target as HTMLElement).tagName === "TEXTAREA" || (e.target as HTMLElement).tagName === "INPUT") return;

    const activeFlag = displayFlags[activeFlagIdx]?.flag;

    switch (e.key.toLowerCase()) {
      case "j":
        if (displayFlags.length === 0) break;
        setActiveFlagIdx((i) => Math.min(displayFlags.length - 1, i + 1));
        break;
      case "k":
        if (displayFlags.length === 0) break;
        setActiveFlagIdx((i) => Math.max(0, i - 1));
        break;
      case "c":
        if (activeFlag) {
          const code = activeFlag.ruleCode;
          setDecisions((x) => ({ ...x, [code]: { ...x[code], decision: "CONFIRM", notes: x[code]?.notes ?? "" } }));
        }
        break;
      case "o":
        if (activeFlag) {
          const code = activeFlag.ruleCode;
          setDecisions((x) => ({ ...x, [code]: { ...x[code], decision: "OVERRIDE", notes: x[code]?.notes ?? "" } }));
        }
        break;
      case "?":
        setShowShortcuts((v) => !v);
        break;
      case "f":
        toggleTranscriptFullscreen();
        break;
      case "b":
        setQueueOpen((open) => !open);
        break;
      case "escape":
        setDrawerOpen(false);
        setShowShortcuts(false);
        break;
      default: {
        const num = parseInt(e.key);
        if (num >= 1 && num <= pageCount) setCurrentPage(num);
        break;
      }
    }
  }, [displayFlags, activeFlagIdx, pageCount, toggleTranscriptFullscreen]);

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  useEffect(() => {
    let cancelled = false;
    const loadQueue = () => {
      listApplications({ statuses: ["READY_FOR_REVIEW"] })
        .then((items) => {
          if (!cancelled) setQueueApps(items);
        })
        .catch(() => {
          if (!cancelled) setQueueApps([]);
        });
    };
    loadQueue();
    const interval = window.setInterval(loadQueue, 8000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setIsAppLoading(true);
    setApp(null);
    setFlags([]);
    setExtraction({ physical: [], content: [], program: [] });
    setError(null);
    setActiveFlagIdx(0);
    setDecisions({});
    setCurrentPage(1);
    transcriptZoomRef.current = DEFAULT_TRANSCRIPT_ZOOM;
    setTranscriptZoom(DEFAULT_TRANSCRIPT_ZOOM);
    setOverallDecision(null);
    setSubmitModalOpen(false);
    setDrawerOpen(false);
    getApplication(id)
      .then((data) => {
        if (cancelled) return;
        setApp(data.application);
        setFlags(data.flags);
        const ext = data.extraction;
        const hasData = ext.physical.length > 0 || ext.content.length > 0 || ext.program.length > 0;
        setExtraction(hasData ? ext : buildFallbackExtraction(data.application));
        setIsAppLoading(false);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message);
        setApp(null);
        setFlags([]);
        setIsAppLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (error) {
    return (
      <ReviewStateScreen
        title="Application could not load"
        message={`${error}. This usually means the record is no longer reviewable, the API rejected the request, or the application ID is stale.`}
        onBack={() => navigate(APP_ROUTES.queue)}
        embedded={embedded}
      />
    );
  }

  const reviewableQueueApps = [...queueApps
    .filter((a) => a.status === "READY_FOR_REVIEW")
    .filter(hasExtractedSummary)]
    .sort((a, b) => {
      if (queueSort === "newest") {
        return a.ageHours - b.ageHours || b.flagCount - a.flagCount;
      }
      if (queueSort === "flags") {
        return b.flagCount - a.flagCount || b.ageHours - a.ageHours;
      }
      if (queueSort === "severity") {
        return appSeverityRank(a.highestSeverity) - appSeverityRank(b.highestSeverity)
          || b.flagCount - a.flagCount
          || b.ageHours - a.ageHours;
      }
      if (queueSort === "applicant") {
        return (a.applicantName || a.originalFilename).localeCompare(b.applicantName || b.originalFilename)
          || b.ageHours - a.ageHours;
      }
      if (queueSort === "institution") {
        return (a.institution || "").localeCompare(b.institution || "")
          || b.ageHours - a.ageHours;
      }
      return b.ageHours - a.ageHours || b.flagCount - a.flagCount;
    });

  if (!isAppLoading && app && flags.length === 0 && app.flagCount > 0) {
    return (
      <ReviewStateScreen
        title="Flag details are not available"
        message={`${app.applicantName || app.applicationId} is listed with ${app.flagCount} flag${app.flagCount === 1 ? "" : "s"}, but the detail API returned no flag records. This usually means the queue row is stale or processing has not finished writing the flag items.`}
        onBack={() => navigate(APP_ROUTES.queue)}
        embedded={embedded}
      />
    );
  }

  const resolvedCount = flags.filter((f) => decisions[f.ruleCode]?.decision).length;
  const allDecided = flags.length === 0 || resolvedCount === flags.length;
  const allOverridesNoted = flags.every((f) => {
    const d = decisions[f.ruleCode];
    if (!d?.decision) return false;
    if (d.decision !== "OVERRIDE") return true;
    return (d.notes ?? "").trim().length > 0;
  });
  const canSubmit = allDecided && allOverridesNoted && !isAppLoading && !!app;
  const jumpTo = (flag: Flag) => setCurrentPage(flag.sourceLocation.page);
  const openDrawer = (flag: Flag | null) => { setDrawerFlag(flag); setDrawerOpen(true); };
  const showQueueSidebar = queueOpen && !isTablet && !isPhone;
  const reviewGridTemplateColumns = isPhone
    ? "1fr"
    : showQueueSidebar
      ? "220px minmax(0, 1fr) minmax(280px, 340px)"
      : "minmax(0, 1fr) minmax(280px, 360px)";
  const reviewGridTemplateRows = embedded
    ? isPhone
      ? "minmax(320px, 48vh) minmax(0, 1fr)"
      : "1fr"
    : isPhone
      ? "auto minmax(320px, 48vh) minmax(0, 1fr)"
      : "auto 1fr";

  const handleSubmit = async () => {
    if (!canSubmit || !id || !overallDecision) return;
    setIsSubmitting(true);
    const flagDecisions = flags
      .filter((f) => decisions[f.ruleCode]?.decision)
      .map((f) => ({
        ruleCode: f.ruleCode,
        decision: decisions[f.ruleCode].decision!,
        notes: decisions[f.ruleCode].notes ?? "",
      }));
    try {
      await submitDecision(id, { flagDecisions, overallDecision: overallDecision! });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Submit failed";
      setToast(`Submit error: ${msg}. Navigating anyway for review.`);
      setIsSubmitting(false);
      setSubmitModalOpen(false);
      setTimeout(() => navigate(applicationReviewedPath(id), reviewedBackState), 2200);
      return;
    }
    setIsSubmitting(false);
    setSubmitModalOpen(false);
    setToast(`Decision recorded for ${app?.applicantName || app?.applicationId || id}.`);
    setTimeout(() => navigate(applicationReviewedPath(id), reviewedBackState), 1800);
  };

  return (
    <div style={{
      width: embedded ? "100%" : "100vw", height: embedded ? "100%" : "100vh", position: "relative",
      background: t.bg, fontFamily: "'Open Sans', system-ui, sans-serif", color: t.ink,
      display: "grid",
      gridTemplateColumns: reviewGridTemplateColumns,
      gridTemplateRows: reviewGridTemplateRows,
      overflow: "hidden",
    }}>
      {!embedded && <div style={{
        gridColumn: "1 / -1", borderBottom: `3px solid ${t.accent}`,
        background: t.primary, display: "flex", alignItems: "center", flexWrap: "wrap", padding: isPhone ? "10px 16px" : "10px 22px", gap: 12,
        color: t.primaryInk,
      }}>
        <button onClick={() => setQueueOpen((open) => !open)} style={{
          border: "1px solid rgba(255,255,255,0.2)",
          background: "rgba(255,255,255,0.08)",
          color: "inherit",
          width: 32,
          height: 32,
          borderRadius: 4,
          cursor: "pointer",
          fontSize: 18,
          lineHeight: 1,
          fontFamily: t.mono,
          padding: 0,
        }} title={queueOpen ? "Hide review queue (B)" : "Show review queue (B)"} aria-label={queueOpen ? "Hide review queue" : "Show review queue"}>
          &#9776;
        </button>
        <div style={{ display: "flex", alignItems: "center", gap: 12, cursor: "pointer" }} onClick={() => navigate(APP_ROUTES.dashboard)}>
          <div style={{
            width: 30,
            height: 30,
            borderRadius: 6,
            background: t.accent,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: 0.5,
            fontFamily: t.mono,
            color: "#fff",
          }}>
            MS
          </div>
          <div>
            <div style={{
              fontSize: 10,
              opacity: 0.75,
              letterSpacing: 1,
              textTransform: "uppercase",
            }}>
              Mississippi Board of Nursing
            </div>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: t.serif }}>
              Transcript Verification
            </div>
          </div>
        </div>
        <div style={{ height: 20, width: 1, background: "rgba(255,255,255,0.16)" }} />
        <button onClick={() => navigate(APP_ROUTES.dashboard)} style={{
          border: "1px solid rgba(255,255,255,0.2)", background: "rgba(255,255,255,0.08)",
          padding: "4px 10px", fontSize: 11, borderRadius: 2, cursor: "pointer",
          fontFamily: t.mono, color: "rgba(255,255,255,0.82)",
        }}>&larr; Dashboard</button>
        {!isPhone && <div style={{ height: 20, width: 1, background: "rgba(255,255,255,0.16)" }} />}
        {!isNarrow && flags.length > 0 && <ProgressBar total={flags.length} resolved={resolvedCount} />}
        <div style={{ flex: 1 }} />
        {isNarrow && flags.length > 0 && <div style={{ fontSize: 11, fontFamily: t.mono }}>{resolvedCount}/{flags.length} resolved</div>}
        <a href={`https://www.nursys.com`} target="_blank" rel="noopener noreferrer" style={{
          border: "1px solid rgba(255,255,255,0.2)", background: "rgba(255,255,255,0.08)",
          color: "rgba(255,255,255,0.82)", padding: "5px 12px", fontSize: 11, borderRadius: 2,
          fontFamily: t.mono,
          textDecoration: "none", cursor: "pointer",
        }}>Check Nursys &#8599;</a>
        <button onClick={() => setShowShortcuts(true)} style={{
          border: "1px solid rgba(255,255,255,0.2)", background: "rgba(255,255,255,0.08)",
          color: "rgba(255,255,255,0.7)", width: 24, height: 24, fontSize: 13, borderRadius: 2,
          cursor: "pointer", fontFamily: t.mono,
          display: "flex", alignItems: "center", justifyContent: "center", padding: 0,
        }} title="Keyboard shortcuts (?)">?</button>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 12, opacity: 0.85 }}>
            {user?.displayName ?? "Signed in"}
          </span>
          <span style={{
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
          }}>
            {user?.initials ?? "U"}
          </span>
        </div>
      </div>}

      {/* Queue sidebar */}
      <div style={{
        gridColumn: 1,
        gridRow: embedded ? 1 : 2,
        borderRight: showQueueSidebar ? `1px solid ${t.line}` : "none",
        background: `linear-gradient(180deg, ${t.surface} 0%, ${t.surfaceAlt} 100%)`,
        overflow: "hidden",
        display: showQueueSidebar ? "flex" : "none",
        flexDirection: "column",
        padding: showQueueSidebar ? "18px 0" : 0,
      }}>
        <div style={{ padding: "0 18px 10px", borderBottom: `1px solid ${t.line2}`, marginBottom: 8 }}>
          <div style={{
            fontSize: 10,
            color: t.ink4,
            fontFamily: t.mono,
            letterSpacing: 0.8,
            textTransform: "uppercase",
            marginBottom: 4,
          }}>
            Review queue
          </div>
          <div style={{ fontSize: 13, color: t.ink2, marginBottom: 10 }}>
            <span style={{ fontWeight: 600 }}>{reviewableQueueApps.length}</span> pending · sorted by {QUEUE_SORT_LABELS[queueSort]}
          </div>
          <label
            htmlFor="queue-sort"
            style={{
              display: "block",
              fontSize: 10,
              color: t.ink4,
              fontFamily: t.mono,
              letterSpacing: 0.5,
              textTransform: "uppercase",
              marginBottom: 4,
            }}
          >
            Sort queue
          </label>
          <select
            id="queue-sort"
            value={queueSort}
            onChange={(event) => setQueueSort(event.target.value as QueueSort)}
            style={{
              width: "100%",
              height: 30,
              border: `1px solid ${t.line}`,
              background: t.surface,
              color: t.ink2,
              borderRadius: 4,
              padding: "0 8px",
              fontSize: 11,
              fontFamily: t.mono,
              cursor: "pointer",
              outlineColor: t.accent,
              minWidth: 0,
            }}
          >
            <option value="oldest">Oldest first</option>
            <option value="newest">Newest first</option>
            <option value="flags">Most flags</option>
            <option value="severity">Highest severity</option>
            <option value="applicant">Applicant name</option>
            <option value="institution">Institution</option>
          </select>
        </div>
        <div style={{ flex: 1, overflow: "auto" }}>
          {reviewableQueueApps.map((a, index) => (
            <QueueRow key={a.applicationId} app={a} active={a.applicationId === id} shaded={index % 2 === 1}
              onClick={() => navigate(applicationReviewPath(a), detailBackStateFor("queue"))} />
          ))}
        </div>
      </div>

      <style>{`
        #transcript-scroll-viewport::-webkit-scrollbar {
          width: 12px;
          height: 12px;
        }
        #transcript-scroll-viewport::-webkit-scrollbar-track {
          background: ${t.surfaceAlt};
        }
        #transcript-scroll-viewport::-webkit-scrollbar-thumb {
          background: ${t.ink4};
          border: 3px solid ${t.surfaceAlt};
          border-radius: 8px;
        }
        #transcript-scroll-viewport::-webkit-scrollbar-thumb:hover {
          background: ${t.ink3};
        }
      `}</style>

      {/* PDF pane — TranscriptPageViewer */}
      <div id="transcript-preview-pane" ref={transcriptPaneRef} style={{
        gridColumn: isPhone ? 1 : showQueueSidebar ? 2 : 1,
        gridRow: embedded ? 1 : 2,
        background: t.surfaceAlt,
        overflow: "hidden",
        minHeight: 0,
        height: isTranscriptFullscreen ? "100vh" : "100%",
        width: isTranscriptFullscreen ? "100vw" : "auto",
        boxSizing: "border-box",
        position: "relative",
        display: "flex", flexDirection: "column", alignItems: "center",
      }}>
        <div style={{
          width: "100%", maxWidth: isTranscriptFullscreen ? 760 : 560, alignItems: "center", justifyContent: "space-between",
          fontSize: 11, color: t.ink3, fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
          padding: "24px 24px 10px",
          boxSizing: "border-box",
          flexShrink: 0,
          display: isTranscriptFullscreen ? "none" : "flex",
        }}>
          <div>{app ? `${app.applicantName} · ${app.applicationId}` : id}</div>
          <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
            {pages.map((p) => (
              <button key={p} onClick={() => setCurrentPage(p)} style={{
                border: `1px solid ${currentPage === p ? t.ink2 : t.line}`,
                background: currentPage === p ? t.ink : t.surface,
                color: currentPage === p ? "#fff" : t.ink3,
                width: 24, height: 22, fontSize: 11, cursor: "pointer", borderRadius: 2, fontFamily: "inherit",
              }}>{p}</button>
            ))}
          </div>
        </div>
        <div id="transcript-scroll-viewport" ref={transcriptScrollRef} onWheel={handleTranscriptWheel} style={{
          flex: isTranscriptFullscreen ? "none" : 1,
          minHeight: 0,
          width: "100%",
          overflowY: "scroll",
          overflowX: "auto",
          scrollbarGutter: "stable",
          scrollbarColor: `${t.ink4} ${t.surfaceAlt}`,
          display: "flex",
          justifyContent: "center",
          alignItems: "flex-start",
          padding: isTranscriptFullscreen ? "8px 64px 8px 12px" : "0 24px 18px",
          boxSizing: "border-box",
          position: isTranscriptFullscreen ? "absolute" : "relative",
          inset: isTranscriptFullscreen ? 0 : "auto",
          height: isTranscriptFullscreen ? "100%" : "auto",
        }}>
          <div style={{ flexShrink: 0 }}>
            {isAppLoading || !app ? (
              <div style={{
                width: Math.round(560 * ((isTranscriptFullscreen ? 1.35 : 1) * transcriptZoom)),
                minHeight: Math.round(720 * ((isTranscriptFullscreen ? 1.35 : 1) * transcriptZoom)),
                borderRadius: 2,
                background: `linear-gradient(90deg, ${t.line2} 25%, ${t.line} 50%, ${t.line2} 75%)`,
                backgroundSize: "200% 100%",
                animation: "shimmer 1.5s infinite",
                boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
              }} />
            ) : (
              <TranscriptPageViewer
                appId={id!}
                page={currentPage}
                flags={flags}
                pdfScale={(isTranscriptFullscreen ? 1.35 : 1) * transcriptZoom}
              />
            )}
          </div>
        </div>
        {!isTranscriptFullscreen && <div style={{
          display: "flex", alignItems: "center", gap: 8,
          fontSize: 10, color: t.ink4, fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
          padding: "10px 24px 24px",
          boxSizing: "border-box",
          flexShrink: 0,
        }}>
          <span>source: uploaded transcript · nova-pro-v1:0</span>
          <div style={{ height: 12, width: 1, background: t.line }} />
          <button onClick={() => zoomTranscriptBy(-0.1)} style={{
            border: `1px solid ${t.line}`, background: t.surface,
            width: 24, height: 22, fontSize: 13, cursor: "pointer", borderRadius: 2,
            color: t.ink3, fontFamily: "inherit", padding: 0,
          }} title="Zoom out">&minus;</button>
          <button onClick={() => applyTranscriptZoom(DEFAULT_TRANSCRIPT_ZOOM)} style={{
            border: "none", background: "transparent",
            minWidth: 42, height: 22, fontSize: 10, cursor: "pointer",
            color: t.ink4, fontFamily: "inherit", padding: "0 4px",
          }} title="Reset zoom">
            {Math.round(transcriptZoom * 100)}%
          </button>
          <button onClick={() => zoomTranscriptBy(0.1)} style={{
            border: `1px solid ${t.line}`, background: t.surface,
            width: 24, height: 22, fontSize: 13, cursor: "pointer", borderRadius: 2,
            color: t.ink3, fontFamily: "inherit", padding: 0,
          }} title="Zoom in">+</button>
        </div>}
        {isTranscriptFullscreen && (
          <div style={{
            position: "absolute",
            top: 12,
            right: 14,
            bottom: 68,
            width: 42,
            zIndex: 3,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 8,
            padding: "8px 5px",
            boxSizing: "border-box",
            background: t.surface,
            border: `1px solid ${t.line}`,
            borderRadius: 3,
            boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
            fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
          }}>
            <div title={app ? `${app.applicantName} · ${app.applicationId}` : id} style={{
              writingMode: "vertical-rl",
              transform: "rotate(180deg)",
              maxHeight: 220,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              fontSize: 10,
              color: t.ink3,
              lineHeight: 1.1,
            }}>
              {app ? `${app.applicantName} · ${app.applicationId}` : id}
            </div>
            <div style={{ width: 18, height: 1, background: t.line }} />
            {pages.map((p) => (
              <button key={p} onClick={() => setCurrentPage(p)} style={{
                border: `1px solid ${currentPage === p ? t.ink2 : t.line}`,
                background: currentPage === p ? t.ink : t.surface,
                color: currentPage === p ? "#fff" : t.ink3,
                width: 26, height: 24, fontSize: 11, cursor: "pointer", borderRadius: 2, fontFamily: "inherit",
              }}>{p}</button>
            ))}
            <div style={{ width: 18, height: 1, background: t.line }} />
            <button onClick={() => zoomTranscriptBy(-0.1)} style={{
              border: `1px solid ${t.line}`, background: t.surface,
              width: 26, height: 24, fontSize: 14, cursor: "pointer", borderRadius: 2,
              color: t.ink3, fontFamily: "inherit", padding: 0,
            }} title="Zoom out">&minus;</button>
            <button onClick={() => applyTranscriptZoom(DEFAULT_TRANSCRIPT_ZOOM)} style={{
              border: `1px solid ${t.line}`, background: t.surface,
              width: 34, minHeight: 28, fontSize: 9, cursor: "pointer", borderRadius: 2,
              color: t.ink3, fontFamily: "inherit", padding: "2px 0",
            }} title="Reset zoom">
              {Math.round(transcriptZoom * 100)}%
            </button>
            <button onClick={() => zoomTranscriptBy(0.1)} style={{
              border: `1px solid ${t.line}`, background: t.surface,
              width: 26, height: 24, fontSize: 14, cursor: "pointer", borderRadius: 2,
              color: t.ink3, fontFamily: "inherit", padding: 0,
            }} title="Zoom in">+</button>
          </div>
        )}
        <button
          onClick={toggleTranscriptFullscreen}
          aria-label={isTranscriptFullscreen ? "Exit transcript fullscreen" : "Enter transcript fullscreen"}
          title={isTranscriptFullscreen ? "Exit transcript fullscreen (F)" : "Enter transcript fullscreen (F)"}
          style={{
            position: "absolute",
            right: 18,
            bottom: 18,
            zIndex: 4,
            width: 38,
            height: 38,
            borderRadius: 4,
            border: `1px solid ${t.line}`,
            background: t.surface,
            color: t.ink2,
            boxShadow: "0 10px 24px rgba(15,23,42,0.16)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
            fontSize: 18,
            lineHeight: 1,
            padding: 0,
          }}
        >
          ⛶
        </button>
      </div>

      {/* Flag list */}
      <div style={{ gridColumn: isPhone ? 1 : showQueueSidebar ? 3 : 2, gridRow: embedded ? (isPhone ? 2 : 1) : (isPhone ? 3 : 2), background: t.surfaceAlt, borderLeft: isPhone ? "none" : `1px solid ${t.line}`, borderTop: isPhone ? `1px solid ${t.line}` : "none", overflow: "auto", display: "flex", flexDirection: "column" }}>
        <DetailHeader
          compact
          backLabel="Review Queue"
          backTo="/queue"
          eyebrow="Review detail"
          title={app?.applicantName || "Loading application"}
          subtitle={app ? `${app.institution} · license ${app.licenseNumber}` : "Loading application details"}
          style={{
            background: `linear-gradient(180deg, ${t.surface} 0%, ${t.surfaceAlt} 100%)`,
            boxShadow: "0 8px 24px rgba(15,23,42,0.06)",
          }}
          statusSummary={
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
              <Stat label="flags" value={`${flags.length}`} />
              <Stat label="high" value={`${flags.filter((f) => f.severity === "High").length}`} />
              <Stat label="pages" value={`${app?.pageCount ?? 0}`} />
              <Stat label="uploaded" value={app?.submittedAt ? new Date(app.submittedAt).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "Not available"} />
            </div>
          }
          secondaryActions={
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {flags.length > 0 && <ProgressBar total={flags.length} resolved={resolvedCount} />}
              <div style={{ display: "flex", gap: 8 }}>
                <a href="https://www.nursys.com" target="_blank" rel="noopener noreferrer" style={{
                  border: `1px solid ${t.line}`,
                  background: t.surface,
                  color: t.ink2,
                  padding: "5px 9px",
                  fontSize: 10,
                  borderRadius: 3,
                  fontFamily: t.mono,
                  textDecoration: "none",
                  cursor: "pointer",
                }}>Nursys &#8599;</a>
                <button onClick={() => setShowShortcuts(true)} style={{
                  border: `1px solid ${t.line}`,
                  background: t.surface,
                  color: t.ink3,
                  width: 26,
                  height: 26,
                  fontSize: 13,
                  borderRadius: 3,
                  cursor: "pointer",
                  fontFamily: t.mono,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  padding: 0,
                }} title="Keyboard shortcuts (?)" aria-label="Keyboard shortcuts">?</button>
              </div>
            </div>
          }
          primaryActions={
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, paddingTop: 12, borderTop: `1px solid ${t.line2}` }}>
              <div style={{ fontSize: 10, color: t.ink4, fontFamily: t.mono, letterSpacing: 0.5, textTransform: "uppercase" }}>
                Review controls
              </div>
              <div style={{ fontSize: 10, color: t.ink4, fontFamily: t.mono }}>
                {allDecided ? "ready to submit" : `${flags.length - resolvedCount} remaining`}
              </div>
            </div>
          }
        />

        <div style={{ flex: 1, overflow: "auto", padding: "14px 14px 84px" }}>
          <div style={{ marginBottom: 12 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 8 }}>
              <div style={{ fontSize: 10, color: t.ink4, fontFamily: t.mono, letterSpacing: 0.5, textTransform: "uppercase" }}>
                Flags raised — {resolvedCount} / {flags.length} resolved
              </div>
              <div style={{ fontSize: 10, color: t.ink4, fontFamily: t.mono, textTransform: "uppercase", letterSpacing: 0.4 }}>
                Sort
              </div>
            </div>
            <div
              role="group"
              aria-label="Sort flags"
              style={{
                display: "grid",
                gridTemplateColumns: isPhone ? "repeat(2, minmax(0, 1fr))" : "repeat(4, minmax(0, 1fr))",
                gap: 6,
              }}
            >
              {([
                ["severity", "Severity"],
                ["rule", "Rule"],
                ["page", "Page"],
                ["status", "Status"],
              ] as const).map(([value, label]) => {
                const active = flagSort === value;
                return (
                  <button
                    key={value}
                    onClick={() => setFlagSort(value)}
                    style={{
                      height: 30,
                      border: `1px solid ${active ? t.accent : t.line}`,
                      background: active ? t.accentBg : t.surface,
                      color: active ? t.accent : t.ink3,
                      borderRadius: 4,
                      cursor: "pointer",
                      fontFamily: t.mono,
                      fontSize: 10,
                      fontWeight: 800,
                      textTransform: "uppercase",
                      letterSpacing: 0.3,
                    }}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
          {isAppLoading && Array.from({ length: 3 }, (_, index) => (
            <div key={index} style={{
              height: 136,
              marginBottom: 10,
              borderRadius: 3,
              background: `linear-gradient(90deg, ${t.line2} 25%, ${t.line} 50%, ${t.line2} 75%)`,
              backgroundSize: "200% 100%",
              animation: "shimmer 1.5s infinite",
            }} />
          ))}
          {!isAppLoading && sortedFlagGroups.map((group) => (
            <div
              key={group.ruleCode}
              style={{
                marginBottom: 12,
                background: group.groupIndex % 2 === 1 ? t.surfaceAlt : "transparent",
                border: `1px solid ${group.groupIndex % 2 === 1 ? t.line : "transparent"}`,
                borderRadius: 6,
                padding: group.groupIndex % 2 === 1 ? "8px 7px 2px" : "0",
              }}
            >
              <div style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 10,
                marginBottom: 8,
                padding: "0 2px",
              }}>
                <div style={{
                  fontSize: 11,
                  fontWeight: 700,
                  color: t.ink2,
                  fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
                  letterSpacing: 0.3,
                }}>
                  {group.ruleCode}
                </div>
                <div style={{
                  fontSize: 10,
                  color: t.ink4,
                  fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
                  textTransform: "uppercase",
                }}>
                  {group.items.length} flag{group.items.length === 1 ? "" : "s"}
                </div>
              </div>
              {group.items.map(({ flag, originalIndex }) => {
                const displayIndex = displayFlags.findIndex((item) => item.originalIndex === originalIndex);

                return (
                  <FlagCard key={`${flag.ruleCode}-${originalIndex}`} flag={flag} active={displayIndex === activeFlagIdx}
                    shaded={group.groupIndex % 2 === 1}
                    decision={decisions[flag.ruleCode]?.decision}
                    notes={decisions[flag.ruleCode]?.notes}
                    onClick={() => setActiveFlagIdx(displayIndex)}
                    onDecision={(d) => setDecisions((x) => ({ ...x, [flag.ruleCode]: { ...x[flag.ruleCode], decision: d, notes: x[flag.ruleCode]?.notes ?? "" } }))}
                    onNotes={(n) => setDecisions((x) => ({ ...x, [flag.ruleCode]: { ...x[flag.ruleCode], decision: x[flag.ruleCode]?.decision, notes: n } }))}
                    onJumpTo={() => jumpTo(flag)}
                    onOpenData={() => openDrawer(flag)}
                  />
                );
              })}
            </div>
          ))}
          <button onClick={() => openDrawer(null)} style={{
            width: "100%", marginTop: 4, padding: "9px 12px",
            background: t.surface, border: `1px dashed ${t.line}`,
            fontSize: 11, color: t.ink3, cursor: "pointer",
            borderRadius: 2, fontFamily: t.mono,
          }}>
            View all extraction fields ({totalFields}) &rarr;
          </button>
        </div>
      </div>

      <button
        disabled={!canSubmit}
        onClick={() => {
          if (canSubmit) setSubmitModalOpen(true);
        }}
        aria-label="Submit decision"
        title="Submit decision"
        style={{
          position: "absolute",
          right: 28,
          bottom: 28,
          zIndex: 25,
          width: 52,
          height: 52,
          borderRadius: "50%",
          background: canSubmit ? t.accent : "rgba(10, 31, 61, 0.72)",
          color: "#fff",
          border: `1px solid ${canSubmit ? "rgba(255,255,255,0.14)" : t.primary}`,
          padding: 0,
          fontSize: 22,
          lineHeight: 1,
          cursor: canSubmit ? "pointer" : "not-allowed",
          boxShadow: "0 12px 34px rgba(0,0,0,0.32)",
          opacity: canSubmit ? 1 : 0.72,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          transition: "background 140ms, opacity 140ms",
        }}
      >
        &#10132;
      </button>

      {/* Extracted data drawer */}
      {drawerOpen && (
        <ExtractedDataDrawer flag={drawerFlag} extraction={extraction} onClose={() => setDrawerOpen(false)} />
      )}

      {submitModalOpen && (
        <SubmitDecisionModal
          overallDecision={overallDecision}
          onSelect={setOverallDecision}
          onClose={() => setSubmitModalOpen(false)}
          onSubmit={handleSubmit}
          isSubmitting={isSubmitting}
        />
      )}

      {/* Keyboard shortcut legend */}
      {showShortcuts && <ShortcutLegend onClose={() => setShowShortcuts(false)} />}

      {/* Toast notification */}
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  );
}
