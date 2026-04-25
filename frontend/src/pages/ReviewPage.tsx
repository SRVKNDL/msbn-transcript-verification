import { useState, useEffect, useCallback, useRef } from "react";
import type { WheelEvent } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { TOKENS, LAYOUT } from "../tokens";
import { SeverityChip } from "../components/SeverityChip";
import { ConfidenceDot } from "../components/ConfidenceDot";
import { ProgressBar } from "../components/ProgressBar";
import { ActionButton } from "../components/ActionButton";
import { getApplication, getPageImage, listApplications, submitDecision } from "../api";
import { getCurrentUser } from "../auth";
import type { Application, Flag, Decisions, OverallDecision, ExtractionData, ExtractionRow } from "../types";

// --- Toast notification ---
function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  useEffect(() => {
    const t = setTimeout(onClose, 3500);
    return () => clearTimeout(t);
  }, [onClose]);

  return (
    <div style={{
      position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)",
      background: TOKENS.ink, color: "#fff", padding: "12px 24px",
      borderRadius: 4, fontSize: 13, fontWeight: 500, zIndex: 100,
      boxShadow: "0 8px 24px rgba(0,0,0,0.3)",
      fontFamily: "'Open Sans', system-ui, sans-serif",
      animation: "toastIn 300ms cubic-bezier(.2,.7,.3,1)",
    }}>
      <span style={{ marginRight: 8, color: TOKENS.ok }}>&#10003;</span>
      {message}
    </div>
  );
}

// --- Keyboard shortcut legend ---
function ShortcutLegend({ onClose }: { onClose: () => void }) {
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
        background: TOKENS.paper, borderRadius: 4, padding: "24px 32px",
        boxShadow: "0 20px 60px rgba(0,0,0,0.3)", minWidth: 280,
        border: `1px solid ${LAYOUT.line}`,
      }}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 14 }}>Keyboard shortcuts</div>
        {shortcuts.map(([key, desc]) => (
          <div key={key} style={{ display: "flex", gap: 14, alignItems: "center", marginBottom: 8 }}>
            <span style={{
              fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
              fontSize: 11, fontWeight: 600, background: TOKENS.bg,
              border: `1px solid ${TOKENS.line}`, borderRadius: 2,
              padding: "2px 8px", minWidth: 40, textAlign: "center",
            }}>{key}</span>
            <span style={{ fontSize: 12, color: TOKENS.ink2 }}>{desc}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function timeAgo(hrs: number) {
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: TOKENS.ink4, fontFamily: "'IBM Plex Mono', ui-monospace, monospace", letterSpacing: 0.4, textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: 14, color: TOKENS.ink, fontWeight: 600, fontFamily: "'IBM Plex Mono', ui-monospace, monospace" }}>{value}</div>
    </div>
  );
}

function hasExtractedSummary(app: Application) {
  return Boolean(app.applicantName.trim() || app.institution.trim());
}

function ReviewStateScreen({
  title,
  message,
  onBack,
}: {
  title: string;
  message: string;
  onBack: () => void;
}) {
  return (
    <div style={{
      width: "100vw",
      height: "100vh",
      background: LAYOUT.bg,
      color: TOKENS.ink,
      fontFamily: "'Open Sans', system-ui, sans-serif",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: 24,
      boxSizing: "border-box",
    }}>
      <div style={{
        width: "min(520px, 100%)",
        background: TOKENS.paper,
        border: `1px solid ${TOKENS.line}`,
        borderTop: `3px solid ${TOKENS.high}`,
        borderRadius: 3,
        padding: "24px 28px",
        boxShadow: "0 18px 45px rgba(0,0,0,0.16)",
      }}>
        <div style={{
          fontSize: 11,
          color: TOKENS.ink4,
          fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
          letterSpacing: 0.6,
          textTransform: "uppercase",
          marginBottom: 8,
        }}>
          Review detail
        </div>
        <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 10, fontFamily: "'Montserrat', system-ui, sans-serif" }}>
          {title}
        </div>
        <div style={{ fontSize: 13, color: TOKENS.ink2, lineHeight: 1.6, marginBottom: 18 }}>
          {message}
        </div>
        <button onClick={onBack} style={{
          border: "none",
          background: TOKENS.ink,
          color: "#fff",
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
      background: TOKENS.paper,
      border: `1px solid ${TOKENS.line}`, borderRadius: 2,
      boxShadow: "0 8px 24px rgba(0,0,0,0.16)",
      display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 16,
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: "50%",
        border: `3px solid ${TOKENS.line}`, borderTopColor: LAYOUT.accent,
        animation: "txSpin 0.8s linear infinite",
      }} />
      <div style={{ fontSize: 12, color: TOKENS.ink4, fontFamily: "'IBM Plex Mono', monospace" }}>
        Fetching page {page} from S3…
      </div>
      <style>{`@keyframes txSpin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );

  if (status === "loaded" && imgUrl) return (
    <div style={{
      width: Math.round(560 * pdfScale), background: TOKENS.paper,
      border: `1px solid ${TOKENS.line}`, borderRadius: 2,
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
          background: f.severity === "High" ? TOKENS.highBg : f.severity === "Medium" ? TOKENS.medBg : TOKENS.lowBg,
          border: `1px solid ${f.severity === "High" ? TOKENS.high : f.severity === "Medium" ? TOKENS.med : TOKENS.low}`,
          borderRadius: 4, padding: "4px 10px",
          fontSize: 10, fontFamily: "'IBM Plex Mono', monospace",
          color: f.severity === "High" ? TOKENS.high : f.severity === "Medium" ? TOKENS.med : TOKENS.low,
          fontWeight: 600,
        }}>&#9873; {f.ruleCode} · {f.severity}</div>
      ))}
    </div>
  );

  return (
    <div style={{
      width: Math.round(560 * pdfScale), minHeight: Math.round(720 * pdfScale),
      background: TOKENS.paper,
      border: `1px solid ${TOKENS.line}`,
      boxShadow: "0 8px 24px rgba(0,0,0,0.16)",
      padding: "36px 42px", boxSizing: "border-box",
      display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      textAlign: "center", color: TOKENS.ink3,
    }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: TOKENS.ink, fontFamily: "'Montserrat', system-ui, sans-serif", marginBottom: 8 }}>
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
function QueueRow({ app, active, onClick }: { app: Application; active: boolean; onClick: () => void }) {
  return (
    <div onClick={onClick} style={{
      display: "grid", gridTemplateColumns: "14px 1fr 90px 60px 70px",
      gap: 12, alignItems: "center", padding: "9px 14px",
      borderBottom: `1px solid ${TOKENS.line2}`,
      background: active ? TOKENS.line2 : "transparent",
      cursor: "pointer", fontSize: 13, color: TOKENS.ink2,
    }}>
      <div style={{ width: 6, height: 6, borderRadius: 3,
        background: app.highestSeverity === "High" ? TOKENS.high
          : app.highestSeverity === "Medium" ? TOKENS.med
          : app.highestSeverity === "Low" ? TOKENS.low : TOKENS.ink5 }} />
      <div>
        <div style={{ fontWeight: 500, color: TOKENS.ink }}>{app.applicantName}</div>
        <div style={{ fontSize: 11, color: TOKENS.ink4, fontFamily: "'IBM Plex Mono', ui-monospace, monospace", marginTop: 1 }}>{app.applicationId}</div>
      </div>
      <div style={{ fontSize: 11, color: TOKENS.ink3, fontFamily: "'IBM Plex Mono', ui-monospace, monospace" }}>
        {app.country} · {app.programYear}
      </div>
      <div style={{ fontSize: 11, color: app.flagCount ? TOKENS.ink2 : TOKENS.ink4, fontFamily: "'IBM Plex Mono', ui-monospace, monospace" }}>
        {app.flagCount} flag{app.flagCount !== 1 ? "s" : ""}
      </div>
      <div style={{ fontSize: 11, color: TOKENS.ink3, fontFamily: "'IBM Plex Mono', ui-monospace, monospace", textAlign: "right" }}>
        {timeAgo(app.ageHours)}
      </div>
    </div>
  );
}

// --- Flag card ---
function FlagCard({ flag, decision, notes, onDecision, onNotes, onJumpTo, onOpenData, active, onClick }: {
  flag: Flag; decision?: string; notes?: string;
  onDecision: (d: "CONFIRM" | "OVERRIDE") => void; onNotes: (n: string) => void;
  onJumpTo: () => void; onOpenData: () => void;
  active: boolean; onClick: () => void;
}) {
  const resolved = !!decision;
  return (
    <div onClick={onClick} style={{
      border: `1px solid ${active ? TOKENS.ink3 : TOKENS.line}`,
      borderLeft: `3px solid ${flag.severity === "High" ? TOKENS.high : flag.severity === "Medium" ? TOKENS.med : TOKENS.low}`,
      background: resolved ? LAYOUT.line2 : TOKENS.paper,
      opacity: resolved && !active ? 0.72 : 1,
      borderRadius: 2, padding: "12px 14px", cursor: "pointer", marginBottom: 8,
      transition: "background 140ms, opacity 140ms",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
        <span style={{ fontFamily: "'IBM Plex Mono', ui-monospace, monospace", fontSize: 12, fontWeight: 600, color: TOKENS.ink }}>{flag.ruleCode}</span>
        <SeverityChip severity={flag.severity} />
        {resolved && (
          <span style={{
            fontFamily: "'IBM Plex Mono', ui-monospace, monospace", fontSize: 10, fontWeight: 600,
            color: decision === "CONFIRM" ? TOKENS.high : TOKENS.ok,
            background: decision === "CONFIRM" ? TOKENS.highBg : TOKENS.okBg,
            padding: "2px 7px", borderRadius: 2, letterSpacing: 0.3,
          }}>
            {decision === "CONFIRM" ? "\u2713 CONFIRMED" : "\u2713 OVERRIDDEN"}
          </span>
        )}
        <span style={{ fontSize: 10, color: TOKENS.ink4, fontFamily: "'IBM Plex Mono', ui-monospace, monospace", marginLeft: "auto" }}>
          {flag.safePractice}
        </span>
      </div>
      <div style={{ fontSize: 12, color: TOKENS.ink2, fontWeight: 500, marginBottom: 4 }}>
        {flag.ruleName.replaceAll("_", " ").toLowerCase()}
      </div>
      <div style={{ fontSize: 12, color: TOKENS.ink3, lineHeight: 1.55, marginBottom: 10 }}>
        {flag.rationale}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: TOKENS.ink4, flexWrap: "wrap" }}>
        <button onClick={(e) => { e.stopPropagation(); onJumpTo(); }} style={{
          border: `1px solid ${TOKENS.line}`, background: TOKENS.bg,
          fontSize: 10, padding: "3px 8px", borderRadius: 2, cursor: "pointer",
          fontFamily: "'IBM Plex Mono', ui-monospace, monospace", color: TOKENS.ink2,
        }}>
          &darr; page {flag.sourceLocation.page}
        </button>
        <button onClick={(e) => { e.stopPropagation(); onOpenData(); }} style={{
          border: `1px solid ${TOKENS.line}`, background: TOKENS.bg,
          fontSize: 10, padding: "3px 8px", borderRadius: 2, cursor: "pointer",
          fontFamily: "'IBM Plex Mono', ui-monospace, monospace", color: TOKENS.ink2,
        }}>
          # data
        </button>
        <span style={{ fontSize: 10, fontFamily: "'IBM Plex Mono', ui-monospace, monospace" }}>
          "{flag.sourceLocation.spans[0]}"
        </span>
      </div>

      {active && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px dashed ${TOKENS.line}` }}>
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
                border: `1px solid ${TOKENS.line}`, borderRadius: 2,
                padding: 8, fontSize: 12, fontFamily: "inherit", color: TOKENS.ink2,
                background: TOKENS.bg, resize: "vertical",
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
        width: 500, background: TOKENS.paper, height: "100%",
        borderLeft: `1px solid ${LAYOUT.line}`, display: "flex", flexDirection: "column",
        boxShadow: "-20px 0 50px rgba(0,0,0,0.18)",
        animation: "drawerSlide 220ms cubic-bezier(.2,.7,.3,1)",
      }}>
        <div style={{ padding: "18px 22px 12px", borderBottom: `1px solid ${TOKENS.line}` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <span style={{ fontSize: 10, fontFamily: "'IBM Plex Mono', ui-monospace, monospace", color: TOKENS.ink4, letterSpacing: 0.5, textTransform: "uppercase" }}>Extracted fields</span>
            <div style={{ flex: 1 }} />
            <button onClick={onClose} style={{
              border: "none", background: "transparent", cursor: "pointer",
              color: TOKENS.ink3, fontSize: 16, padding: 0, lineHeight: 1,
            }}>&times;</button>
          </div>
          <div style={{ fontSize: 16, fontWeight: 600, color: TOKENS.ink, marginBottom: 4, fontFamily: "'Montserrat', system-ui, sans-serif" }}>Bedrock Nova extraction</div>
          <div style={{ fontSize: 11, color: TOKENS.ink4, fontFamily: "'IBM Plex Mono', ui-monospace, monospace" }}>
            nova-pro-v1:0 · prompt v1.2 · extracted 2026-04-19 14:24 UTC
          </div>
          {flag && (
            <div style={{
              marginTop: 12, padding: "7px 10px",
              background: TOKENS.highBg, border: `1px solid ${TOKENS.highBgStrong}`,
              borderRadius: 2, fontSize: 11, color: TOKENS.ink2,
              fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
            }}>
              showing fields related to <b style={{ color: TOKENS.high }}>{flag.ruleCode}</b>
            </div>
          )}
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: 0, borderBottom: `1px solid ${TOKENS.line}`, padding: "0 22px" }}>
          {TABS.map((t) => (
            <button key={t.key} onClick={() => setTab(t.key)} style={{
              border: "none", background: "transparent", cursor: "pointer",
              padding: "10px 14px 10px 0", marginRight: 18,
              fontSize: 12, fontWeight: tab === t.key ? 600 : 400,
              color: tab === t.key ? TOKENS.ink : TOKENS.ink3,
              borderBottom: `2px solid ${tab === t.key ? LAYOUT.accent : "transparent"}`,
              marginBottom: -1, fontFamily: "inherit",
            }}>
              {t.label} <span style={{ color: TOKENS.ink4, fontFamily: "'IBM Plex Mono', ui-monospace, monospace", fontSize: 11 }}>{t.count}</span>
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
                background: hi ? TOKENS.highBg : "transparent",
                borderLeft: hi ? `3px solid ${TOKENS.high}` : "3px solid transparent",
                borderBottom: `1px solid ${TOKENS.line2}`,
              }}>
                <div style={{
                  fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
                  fontSize: 11, color: hi ? TOKENS.ink : TOKENS.ink3, fontWeight: hi ? 600 : 400,
                }}>{row.field}</div>
                <div style={{ fontSize: 12, color: TOKENS.ink2, fontFamily: "'IBM Plex Mono', ui-monospace, monospace" }}>{row.value}</div>
                <ConfidenceDot level={row.confidence} />
              </div>
            );
          })}
        </div>

        <div style={{ padding: "12px 22px", borderTop: `1px solid ${TOKENS.line}`, fontSize: 10, color: TOKENS.ink4, fontFamily: "'IBM Plex Mono', ui-monospace, monospace" }}>
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
export function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const user = getCurrentUser();

  const [app, setApp] = useState<Application | null>(null);
  const [queueApps, setQueueApps] = useState<Application[]>([]);
  const [flags, setFlags] = useState<Flag[]>([]);
  const [extraction, setExtraction] = useState<ExtractionData>({ physical: [], content: [], program: [] });
  const [error, setError] = useState<string | null>(null);
  const [activeFlagIdx, setActiveFlagIdx] = useState(0);
  const [decisions, setDecisions] = useState<Decisions>({});
  const [currentPage, setCurrentPage] = useState(1);
  const [overallDecision, setOverallDecision] = useState<OverallDecision>(null);
  const [drawerFlag, setDrawerFlag] = useState<Flag | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [queueOpen, setQueueOpen] = useState(true);
  const [isTranscriptFullscreen, setIsTranscriptFullscreen] = useState(false);
  const [transcriptZoom, setTranscriptZoom] = useState(1);
  const transcriptPaneRef = useRef<HTMLDivElement>(null);
  const transcriptScrollRef = useRef<HTMLDivElement>(null);
  const transcriptZoomRef = useRef(1);

  const pageCount = Math.max(1, app?.pageCount || 1);
  const pages = Array.from({ length: pageCount }, (_, i) => i + 1);
  const totalFields = extraction.physical.length + extraction.content.length + extraction.program.length;

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

    switch (e.key.toLowerCase()) {
      case "j":
        setActiveFlagIdx((i) => Math.min(flags.length - 1, i + 1));
        break;
      case "k":
        setActiveFlagIdx((i) => Math.max(0, i - 1));
        break;
      case "c":
        if (flags[activeFlagIdx]) {
          const code = flags[activeFlagIdx].ruleCode;
          setDecisions((x) => ({ ...x, [code]: { ...x[code], decision: "CONFIRM", notes: x[code]?.notes ?? "" } }));
        }
        break;
      case "o":
        if (flags[activeFlagIdx]) {
          const code = flags[activeFlagIdx].ruleCode;
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
  }, [flags, activeFlagIdx, pageCount, toggleTranscriptFullscreen]);

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  useEffect(() => {
    if (!id) return;
    setApp(null);
    setFlags([]);
    setExtraction({ physical: [], content: [], program: [] });
    setError(null);
    setActiveFlagIdx(0);
    setDecisions({});
    setCurrentPage(1);
    setTranscriptZoom(1);
    setOverallDecision(null);
    setDrawerOpen(false);
    getApplication(id)
      .then((data) => {
        setApp(data.application);
        setFlags(data.flags);
        const ext = data.extraction;
        const hasData = ext.physical.length > 0 || ext.content.length > 0 || ext.program.length > 0;
        setExtraction(hasData ? ext : buildFallbackExtraction(data.application));
      })
      .catch((err: Error) => {
        setError(err.message);
        setApp(null);
        setFlags([]);
      });
    listApplications({ statuses: ["READY_FOR_REVIEW"] }).then(setQueueApps).catch(() => setQueueApps([]));
  }, [id]);

  if (error) {
    return (
      <ReviewStateScreen
        title="Application could not load"
        message={`${error}. This usually means the record is no longer reviewable, the API rejected the request, or the application ID is stale.`}
        onBack={() => navigate("/queue")}
      />
    );
  }

  if (!app) return (
    <div style={{
      width: "100vw", height: "100vh", background: LAYOUT.bg,
      fontFamily: "'Open Sans', system-ui, sans-serif",
      display: "grid", gridTemplateColumns: "260px 1fr 420px", gridTemplateRows: "44px 1fr",
      overflow: "hidden",
    }}>
      <div style={{ gridColumn: "1 / -1", background: LAYOUT.sidebar, borderBottom: `1px solid ${LAYOUT.line}` }} />
      <div style={{ background: LAYOUT.sidebar, borderRight: `1px solid ${LAYOUT.sidebarBorder}`, padding: 14 }}>
        {[1,2,3].map(i => (
          <div key={i} style={{
            height: 52, marginBottom: 8, borderRadius: 2,
            background: `linear-gradient(90deg, ${TOKENS.line2} 25%, ${TOKENS.line} 50%, ${TOKENS.line2} 75%)`,
            backgroundSize: "200% 100%",
            animation: "shimmer 1.5s infinite",
          }} />
        ))}
      </div>
      <div style={{ background: LAYOUT.pdfBg, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{
          width: 560, height: 720, borderRadius: 2,
          background: `linear-gradient(90deg, ${TOKENS.line2} 25%, ${TOKENS.line} 50%, ${TOKENS.line2} 75%)`,
          backgroundSize: "200% 100%",
          animation: "shimmer 1.5s infinite",
        }} />
      </div>
      <div style={{ background: LAYOUT.bg, borderLeft: `1px solid ${LAYOUT.line}`, padding: 14 }}>
        {[1,2,3].map(i => (
          <div key={i} style={{
            height: 120, marginBottom: 8, borderRadius: 2,
            background: `linear-gradient(90deg, ${TOKENS.line2} 25%, ${TOKENS.line} 50%, ${TOKENS.line2} 75%)`,
            backgroundSize: "200% 100%",
            animation: "shimmer 1.5s infinite",
          }} />
        ))}
      </div>
    </div>
  );

  const reviewableQueueApps = queueApps
    .filter((a) => a.status === "READY_FOR_REVIEW")
    .filter(hasExtractedSummary);

  if (flags.length === 0 && app.flagCount > 0) {
    return (
      <ReviewStateScreen
        title="Flag details are not available"
        message={`${app.applicantName || app.applicationId} is listed with ${app.flagCount} flag${app.flagCount === 1 ? "" : "s"}, but the detail API returned no flag records. This usually means the queue row is stale or processing has not finished writing the flag items.`}
        onBack={() => navigate("/queue")}
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
  const canSubmit = allDecided && allOverridesNoted && !!overallDecision;
  const jumpTo = (flag: Flag) => setCurrentPage(flag.sourceLocation.page);
  const openDrawer = (flag: Flag | null) => { setDrawerFlag(flag); setDrawerOpen(true); };

  const handleSubmit = async () => {
    if (!canSubmit || !id) return;
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
      setTimeout(() => navigate(`/reviewed/${id}`), 2200);
      return;
    }
    setToast(`Decision recorded for ${app.applicantName || app.applicationId}.`);
    setTimeout(() => navigate(`/reviewed/${id}`), 1800);
  };

  return (
    <div style={{
      width: "100vw", height: "100vh", position: "relative",
      background: LAYOUT.bg, fontFamily: "'Open Sans', system-ui, sans-serif", color: TOKENS.ink,
      display: "grid",
      gridTemplateColumns: queueOpen ? "260px 1fr 420px" : "0 1fr 420px",
      gridTemplateRows: "44px 1fr",
      overflow: "hidden",
    }}>
      {/* Top bar */}
      <div style={{
        gridColumn: "1 / -1", borderBottom: `1px solid ${LAYOUT.sidebarBorder}`,
        background: LAYOUT.sidebar, display: "flex", alignItems: "center", padding: "0 18px", gap: 18,
        color: "#fff",
      }}>
        <button onClick={() => setQueueOpen((open) => !open)} style={{
          border: `1px solid ${LAYOUT.sidebarBorder}`,
          background: "rgba(255,255,255,0.08)",
          color: "rgba(255,255,255,0.72)",
          width: 26,
          height: 26,
          borderRadius: 3,
          cursor: "pointer",
          fontSize: 16,
          lineHeight: 1,
          fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
          padding: 0,
        }} title={queueOpen ? "Hide review queue (B)" : "Show review queue (B)"} aria-label={queueOpen ? "Hide review queue" : "Show review queue"}>
          &#9776;
        </button>
        <div style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }} onClick={() => navigate("/dashboard")}>
          <div style={{ width: 20, height: 20, borderRadius: 4, background: "#2563eb", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 9, fontWeight: 700, fontFamily: "'IBM Plex Mono', ui-monospace, monospace" }}>M</div>
          <span style={{ fontSize: 13, fontWeight: 600, letterSpacing: -0.1, fontFamily: "'Montserrat', system-ui, sans-serif" }}>MSBN Review</span>
        </div>
        <div style={{ height: 20, width: 1, background: LAYOUT.sidebarBorder }} />
        <button onClick={() => navigate("/dashboard")} style={{
          border: `1px solid ${LAYOUT.sidebarBorder}`, background: "rgba(255,255,255,0.08)",
          padding: "4px 10px", fontSize: 11, borderRadius: 2, cursor: "pointer",
          fontFamily: "'IBM Plex Mono', ui-monospace, monospace", color: "rgba(255,255,255,0.7)",
        }}>&larr; Dashboard</button>
        <div style={{ height: 20, width: 1, background: LAYOUT.sidebarBorder }} />
        {flags.length > 0 && <ProgressBar total={flags.length} resolved={resolvedCount} />}
        <div style={{ flex: 1 }} />
        <a href={`https://www.nursys.com`} target="_blank" rel="noopener noreferrer" style={{
          border: `1px solid ${LAYOUT.sidebarBorder}`, background: "rgba(255,255,255,0.08)",
          color: "rgba(255,255,255,0.7)", padding: "5px 12px", fontSize: 11, borderRadius: 2,
          fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
          textDecoration: "none", cursor: "pointer",
        }}>Check Nursys &#8599;</a>
        <button onClick={() => setShowShortcuts(true)} style={{
          border: `1px solid ${LAYOUT.sidebarBorder}`, background: "rgba(255,255,255,0.08)",
          color: "rgba(255,255,255,0.5)", width: 24, height: 24, fontSize: 13, borderRadius: 2,
          cursor: "pointer", fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
          display: "flex", alignItems: "center", justifyContent: "center", padding: 0,
        }} title="Keyboard shortcuts (?)">?</button>
        <div style={{ fontSize: 11, color: "rgba(255,255,255,0.5)", fontFamily: "'IBM Plex Mono', ui-monospace, monospace" }}>
          {user?.email || user?.displayName || "Signed in user"}
        </div>
      </div>

      {/* Queue sidebar */}
      <div style={{ gridColumn: 1, gridRow: 2, borderRight: queueOpen ? `1px solid ${LAYOUT.sidebarBorder}` : "none", background: LAYOUT.sidebar, overflow: "hidden", display: queueOpen ? "flex" : "none", flexDirection: "column" }}>
        <div style={{ padding: "12px 14px 10px", borderBottom: `1px solid ${LAYOUT.sidebarBorder}` }}>
          <div style={{ fontSize: 11, color: "rgba(255,255,255,0.5)", fontFamily: "'IBM Plex Mono', ui-monospace, monospace", letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 2 }}>Review queue</div>
          <div style={{ fontSize: 13, color: "rgba(255,255,255,0.8)" }}>
            <span style={{ fontWeight: 600 }}>{reviewableQueueApps.length}</span> pending · sorted by age
          </div>
        </div>
        <div style={{ flex: 1, overflow: "auto" }}>
          {reviewableQueueApps.map((a) => (
            <QueueRow key={a.applicationId} app={a} active={a.applicationId === id}
              onClick={() => navigate(`/review/${a.applicationId}`)} />
          ))}
        </div>
      </div>

      <style>{`
        #transcript-scroll-viewport::-webkit-scrollbar {
          width: 12px;
          height: 12px;
        }
        #transcript-scroll-viewport::-webkit-scrollbar-track {
          background: ${LAYOUT.pdfBg};
        }
        #transcript-scroll-viewport::-webkit-scrollbar-thumb {
          background: ${TOKENS.ink4};
          border: 3px solid ${LAYOUT.pdfBg};
          border-radius: 8px;
        }
        #transcript-scroll-viewport::-webkit-scrollbar-thumb:hover {
          background: ${TOKENS.ink3};
        }
      `}</style>

      {/* PDF pane — TranscriptPageViewer */}
      <div id="transcript-preview-pane" ref={transcriptPaneRef} style={{
        gridColumn: 2,
        gridRow: 2,
        background: LAYOUT.pdfBg,
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
          fontSize: 11, color: TOKENS.ink3, fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
          padding: "24px 24px 10px",
          boxSizing: "border-box",
          flexShrink: 0,
          display: isTranscriptFullscreen ? "none" : "flex",
        }}>
          <div>{app.applicantName} · {app.applicationId}</div>
          <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
            {pages.map((p) => (
              <button key={p} onClick={() => setCurrentPage(p)} style={{
                border: `1px solid ${currentPage === p ? TOKENS.ink2 : TOKENS.line}`,
                background: currentPage === p ? TOKENS.ink : TOKENS.paper,
                color: currentPage === p ? "#fff" : TOKENS.ink3,
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
          scrollbarColor: `${TOKENS.ink4} ${LAYOUT.pdfBg}`,
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
            <TranscriptPageViewer
              appId={id!}
              page={currentPage}
              flags={flags}
              pdfScale={(isTranscriptFullscreen ? 1.35 : 1) * transcriptZoom}
            />
          </div>
        </div>
        {!isTranscriptFullscreen && <div style={{
          display: "flex", alignItems: "center", gap: 8,
          fontSize: 10, color: TOKENS.ink4, fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
          padding: "10px 24px 24px",
          boxSizing: "border-box",
          flexShrink: 0,
        }}>
          <span>source: uploaded transcript · nova-pro-v1:0</span>
          <div style={{ height: 12, width: 1, background: TOKENS.line }} />
          <button onClick={() => zoomTranscriptBy(-0.1)} style={{
            border: `1px solid ${TOKENS.line}`, background: TOKENS.paper,
            width: 24, height: 22, fontSize: 13, cursor: "pointer", borderRadius: 2,
            color: TOKENS.ink3, fontFamily: "inherit", padding: 0,
          }} title="Zoom out">&minus;</button>
          <button onClick={() => applyTranscriptZoom(1)} style={{
            border: "none", background: "transparent",
            minWidth: 42, height: 22, fontSize: 10, cursor: "pointer",
            color: TOKENS.ink4, fontFamily: "inherit", padding: "0 4px",
          }} title="Reset zoom">
            {Math.round(transcriptZoom * 100)}%
          </button>
          <button onClick={() => zoomTranscriptBy(0.1)} style={{
            border: `1px solid ${TOKENS.line}`, background: TOKENS.paper,
            width: 24, height: 22, fontSize: 13, cursor: "pointer", borderRadius: 2,
            color: TOKENS.ink3, fontFamily: "inherit", padding: 0,
          }} title="Zoom in">+</button>
          <div style={{ height: 12, width: 1, background: TOKENS.line }} />
          <button onClick={toggleTranscriptFullscreen} style={{
            border: `1px solid ${TOKENS.line}`, background: TOKENS.paper,
            height: 22, fontSize: 10, cursor: "pointer", borderRadius: 2,
            color: TOKENS.ink3, fontFamily: "inherit", padding: "0 9px",
          }} title="Toggle transcript fullscreen (F)">
            {isTranscriptFullscreen ? "Exit fullscreen" : "Fullscreen"}
          </button>
        </div>}
        {isTranscriptFullscreen && (
          <div style={{
            position: "absolute",
            top: 12,
            right: 14,
            bottom: 12,
            width: 42,
            zIndex: 3,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 8,
            padding: "8px 5px",
            boxSizing: "border-box",
            background: "rgba(203, 213, 225, 0.82)",
            border: `1px solid ${TOKENS.line}`,
            borderRadius: 3,
            boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
            fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
          }}>
            <div title={`${app.applicantName} · ${app.applicationId}`} style={{
              writingMode: "vertical-rl",
              transform: "rotate(180deg)",
              maxHeight: 220,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              fontSize: 10,
              color: TOKENS.ink3,
              lineHeight: 1.1,
            }}>
              {app.applicantName} · {app.applicationId}
            </div>
            <div style={{ width: 18, height: 1, background: TOKENS.line }} />
            {pages.map((p) => (
              <button key={p} onClick={() => setCurrentPage(p)} style={{
                border: `1px solid ${currentPage === p ? TOKENS.ink2 : TOKENS.line}`,
                background: currentPage === p ? TOKENS.ink : TOKENS.paper,
                color: currentPage === p ? "#fff" : TOKENS.ink3,
                width: 26, height: 24, fontSize: 11, cursor: "pointer", borderRadius: 2, fontFamily: "inherit",
              }}>{p}</button>
            ))}
            <div style={{ width: 18, height: 1, background: TOKENS.line }} />
            <button onClick={() => zoomTranscriptBy(-0.1)} style={{
              border: `1px solid ${TOKENS.line}`, background: TOKENS.paper,
              width: 26, height: 24, fontSize: 14, cursor: "pointer", borderRadius: 2,
              color: TOKENS.ink3, fontFamily: "inherit", padding: 0,
            }} title="Zoom out">&minus;</button>
            <button onClick={() => applyTranscriptZoom(1)} style={{
              border: `1px solid ${TOKENS.line}`, background: TOKENS.paper,
              width: 34, minHeight: 28, fontSize: 9, cursor: "pointer", borderRadius: 2,
              color: TOKENS.ink3, fontFamily: "inherit", padding: "2px 0",
            }} title="Reset zoom">
              {Math.round(transcriptZoom * 100)}%
            </button>
            <button onClick={() => zoomTranscriptBy(0.1)} style={{
              border: `1px solid ${TOKENS.line}`, background: TOKENS.paper,
              width: 26, height: 24, fontSize: 14, cursor: "pointer", borderRadius: 2,
              color: TOKENS.ink3, fontFamily: "inherit", padding: 0,
            }} title="Zoom in">+</button>
            <div style={{ flex: 1 }} />
            <button onClick={toggleTranscriptFullscreen} style={{
              border: `1px solid ${TOKENS.line}`,
              background: TOKENS.paper,
              width: 30,
              height: 30,
              fontSize: 16,
              cursor: "pointer",
              borderRadius: 2,
              color: TOKENS.ink3,
              fontFamily: "inherit",
              lineHeight: 1,
            }} title="Exit fullscreen">
              &times;
            </button>
          </div>
        )}
      </div>

      {/* Flag list */}
      <div style={{ gridColumn: 3, gridRow: 2, background: LAYOUT.bg, borderLeft: `1px solid ${LAYOUT.line}`, overflow: "auto", display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "14px 16px", borderBottom: `1px solid ${LAYOUT.line}`, background: TOKENS.paper }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
            <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "'Montserrat', system-ui, sans-serif" }}>{app.applicantName}</div>
            <div style={{ fontSize: 11, color: TOKENS.ink4, fontFamily: "'IBM Plex Mono', ui-monospace, monospace" }}>#{app.applicationId}</div>
          </div>
          <div style={{ fontSize: 12, color: TOKENS.ink3, marginTop: 3 }}>
            {app.institution} · license {app.licenseNumber}
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
            <Stat label="flags" value={`${flags.length}`} />
            <Stat label="high" value={`${flags.filter((f) => f.severity === "High").length}`} />
            <Stat label="pages" value={`${app.pageCount}`} />
            <Stat label="uploaded" value={app.submittedAt ? new Date(app.submittedAt).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "Not available"} />
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12 }}>
            <label htmlFor="overall-decision" style={{
              fontSize: 10,
              color: TOKENS.ink4,
              fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
              letterSpacing: 0.4,
              textTransform: "uppercase",
              whiteSpace: "nowrap",
            }}>
              Decision
            </label>
            <select
              id="overall-decision"
              value={overallDecision ?? ""}
              onChange={(e) =>
                setOverallDecision(e.target.value ? (e.target.value as OverallDecision) : null)
              }
              disabled={!allDecided}
              style={{
                minWidth: 0,
                flex: 1,
                height: 30,
                border: `1px solid ${TOKENS.line}`,
                background: allDecided ? TOKENS.paper : TOKENS.bg,
                color: allDecided ? TOKENS.ink2 : TOKENS.ink4,
                borderRadius: 3,
                padding: "0 8px",
                fontSize: 11,
                fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
                cursor: allDecided ? "pointer" : "not-allowed",
                outlineColor: LAYOUT.accent,
              }}
            >
              <option value="">select decision</option>
              <option value="READY_FOR_LICENSING_REVIEW">ready for licensing review</option>
              <option value="RETURN_TO_APPLICANT">return to applicant</option>
              <option value="DEFERRED">deferred</option>
              <option value="DENIED">denied</option>
            </select>
          </div>
        </div>

        <div style={{ flex: 1, overflow: "auto", padding: "12px 14px" }}>
          <div style={{ fontSize: 10, color: TOKENS.ink4, fontFamily: "'IBM Plex Mono', ui-monospace, monospace", letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 8 }}>
            Flags raised — {resolvedCount} / {flags.length} resolved
          </div>
          {flags.map((flag, i) => (
            <FlagCard key={flag.ruleCode} flag={flag} active={i === activeFlagIdx}
              decision={decisions[flag.ruleCode]?.decision}
              notes={decisions[flag.ruleCode]?.notes}
              onClick={() => setActiveFlagIdx(i)}
              onDecision={(d) => setDecisions((x) => ({ ...x, [flag.ruleCode]: { ...x[flag.ruleCode], decision: d, notes: x[flag.ruleCode]?.notes ?? "" } }))}
              onNotes={(n) => setDecisions((x) => ({ ...x, [flag.ruleCode]: { ...x[flag.ruleCode], decision: x[flag.ruleCode]?.decision, notes: n } }))}
              onJumpTo={() => jumpTo(flag)}
              onOpenData={() => openDrawer(flag)}
            />
          ))}
          <button onClick={() => openDrawer(null)} style={{
            width: "100%", marginTop: 4, padding: "9px 12px",
            background: TOKENS.paper, border: `1px dashed ${TOKENS.line}`,
            fontSize: 11, color: TOKENS.ink3, cursor: "pointer",
            borderRadius: 2, fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
          }}>
            View all extraction fields ({totalFields}) &rarr;
          </button>
        </div>
      </div>

      <button
        disabled={!canSubmit}
        onClick={handleSubmit}
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
          background: canSubmit ? LAYOUT.accent : "rgba(10, 31, 61, 0.72)",
          color: "#fff",
          border: `1px solid ${canSubmit ? "rgba(255,255,255,0.14)" : LAYOUT.sidebarBorder}`,
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

      {/* Keyboard shortcut legend */}
      {showShortcuts && <ShortcutLegend onClose={() => setShowShortcuts(false)} />}

      {/* Toast notification */}
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  );
}
