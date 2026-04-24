import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { TOKENS, LAYOUT } from "../tokens";
import { SeverityChip } from "../components/SeverityChip";
import { ConfidenceDot } from "../components/ConfidenceDot";
import { ProgressBar } from "../components/ProgressBar";
import { ActionButton } from "../components/ActionButton";
import { getApplication, listApplications, submitDecision } from "../api";
import type { Application, Flag, Decisions, OverallDecision, ExtractionData } from "../types";

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
      fontFamily: "'Inter', system-ui, sans-serif",
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
    ["F", "Toggle focus mode"],
    ["1\u20134", "Jump to page"],
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
              fontFamily: "'JetBrains Mono', ui-monospace, monospace",
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
      <div style={{ fontSize: 10, color: TOKENS.ink4, fontFamily: "'JetBrains Mono', ui-monospace, monospace", letterSpacing: 0.4, textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: 14, color: TOKENS.ink, fontWeight: 600, fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}>{value}</div>
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
        <div style={{ fontSize: 11, color: TOKENS.ink4, marginTop: 1 }}>{app.institution}</div>
      </div>
      <div style={{ fontSize: 11, color: TOKENS.ink3, fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}>
        {app.country} · {app.programYear}
      </div>
      <div style={{ fontSize: 11, color: app.flagCount ? TOKENS.ink2 : TOKENS.ink4, fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}>
        {app.flagCount} flag{app.flagCount !== 1 ? "s" : ""}
      </div>
      <div style={{ fontSize: 11, color: TOKENS.ink3, fontFamily: "'JetBrains Mono', ui-monospace, monospace", textAlign: "right" }}>
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
      background: resolved ? LAYOUT.sidebar : TOKENS.paper,
      opacity: resolved && !active ? 0.72 : 1,
      borderRadius: 2, padding: "12px 14px", cursor: "pointer", marginBottom: 8,
      transition: "background 140ms, opacity 140ms",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
        <span style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: 12, fontWeight: 600, color: TOKENS.ink }}>{flag.ruleCode}</span>
        <SeverityChip severity={flag.severity} />
        {resolved && (
          <span style={{
            fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: 10, fontWeight: 600,
            color: decision === "CONFIRM" ? TOKENS.high : TOKENS.ok,
            background: decision === "CONFIRM" ? TOKENS.highBg : TOKENS.okBg,
            padding: "2px 7px", borderRadius: 2, letterSpacing: 0.3,
          }}>
            {decision === "CONFIRM" ? "\u2713 CONFIRMED" : "\u2713 OVERRIDDEN"}
          </span>
        )}
        <span style={{ fontSize: 10, color: TOKENS.ink4, fontFamily: "'JetBrains Mono', ui-monospace, monospace", marginLeft: "auto" }}>
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
          fontFamily: "'JetBrains Mono', ui-monospace, monospace", color: TOKENS.ink2,
        }}>
          &darr; page {flag.sourceLocation.page}
        </button>
        <button onClick={(e) => { e.stopPropagation(); onOpenData(); }} style={{
          border: `1px solid ${TOKENS.line}`, background: TOKENS.bg,
          fontSize: 10, padding: "3px 8px", borderRadius: 2, cursor: "pointer",
          fontFamily: "'JetBrains Mono', ui-monospace, monospace", color: TOKENS.ink2,
        }}>
          # data
        </button>
        <span style={{ fontSize: 10, fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}>
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

// --- Focus mode overlay ---
function FocusMode({ flags, activeIdx, setActiveIdx, decisions, setDecisions, onClose, onOpenData, currentPage, setCurrentPage }: {
  flags: Flag[]; activeIdx: number; setActiveIdx: (i: number) => void;
  decisions: Decisions; setDecisions: React.Dispatch<React.SetStateAction<Decisions>>;
  onClose: () => void; onOpenData: () => void;
  currentPage: number; setCurrentPage: (p: number) => void;
}) {
  const flag = flags[activeIdx];
  const d = decisions[flag.ruleCode];
  const decision = d?.decision;
  const notes = d?.notes;
  const setDecision = (v: "CONFIRM" | "OVERRIDE") =>
    setDecisions((x) => ({ ...x, [flag.ruleCode]: { ...x[flag.ruleCode], decision: v, notes: x[flag.ruleCode]?.notes ?? "" } }));
  const setNotes = (n: string) =>
    setDecisions((x) => ({ ...x, [flag.ruleCode]: { ...x[flag.ruleCode], decision: x[flag.ruleCode]?.decision, notes: n } }));
  const resolvedCount = flags.filter((f) => decisions[f.ruleCode]?.decision).length;

  useEffect(() => { setCurrentPage(flag.sourceLocation.page); }, [activeIdx]);

  return (
    <div style={{
      position: "absolute", inset: 0, background: "rgba(12,18,28,0.55)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 20, backdropFilter: "blur(4px)",
    }}>
      <div style={{
        background: LAYOUT.bg, width: "94%", height: "92%",
        display: "grid", gridTemplateRows: "48px 1fr 60px", gridTemplateColumns: "1fr 440px",
        borderRadius: 4, boxShadow: "0 30px 80px rgba(0,0,0,0.4)",
        overflow: "hidden", border: `1px solid ${LAYOUT.line}`,
      }}>
        {/* Header */}
        <div style={{
          gridColumn: "1 / -1", background: LAYOUT.sidebar, borderBottom: `1px solid ${LAYOUT.line}`,
          display: "flex", alignItems: "center", padding: "0 18px", gap: 14,
        }}>
          <div style={{
            fontSize: 10, fontFamily: "'JetBrains Mono', ui-monospace, monospace",
            color: LAYOUT.accent, fontWeight: 700, letterSpacing: 0.8, textTransform: "uppercase",
            padding: "3px 8px", background: TOKENS.paper, border: `1px solid ${LAYOUT.accent}`, borderRadius: 2,
          }}>&#9670; Focus mode</div>
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            Flag {activeIdx + 1} of {flags.length} · <span style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: 12 }}>{flag.ruleCode}</span>
          </div>
          <div style={{ flex: 1 }} />
          <ProgressBar total={flags.length} resolved={resolvedCount} />
          <button onClick={onClose} style={{
            border: `1px solid ${TOKENS.line}`, background: TOKENS.paper,
            padding: "5px 10px", fontSize: 11, borderRadius: 2, cursor: "pointer",
            fontFamily: "'JetBrains Mono', ui-monospace, monospace", color: TOKENS.ink2,
          }}>exit focus &#10005;</button>
        </div>

        {/* PDF */}
        <div style={{
          background: LAYOUT.pdfBg, overflow: "auto",
          display: "flex", flexDirection: "column", alignItems: "center", padding: 24, gap: 12,
        }}>
          <div style={{ width: "100%", maxWidth: 560, display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 11, color: TOKENS.ink3, fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}>
            <div>Page {currentPage} of 4</div>
            <div style={{ display: "flex", gap: 4 }}>
              {[1, 2, 3, 4].map((p) => (
                <button key={p} onClick={() => setCurrentPage(p)} style={{
                  border: `1px solid ${currentPage === p ? TOKENS.ink2 : TOKENS.line}`,
                  background: currentPage === p ? TOKENS.ink : TOKENS.paper,
                  color: currentPage === p ? "#fff" : TOKENS.ink3,
                  width: 24, height: 22, fontSize: 11, cursor: "pointer", borderRadius: 2, fontFamily: "inherit",
                }}>{p}</button>
              ))}
            </div>
          </div>
          <div style={{ padding: 28, color: TOKENS.ink3 }}>
            Transcript page preview is available from processed S3 page images after deployment wiring.
          </div>
        </div>

        {/* Flag detail */}
        <div style={{ background: TOKENS.paper, padding: "24px 28px", overflow: "auto" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
            <SeverityChip severity={flag.severity} />
            <span style={{ fontSize: 11, color: TOKENS.ink4, fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}>{flag.safePractice}</span>
          </div>
          <div style={{ fontSize: 19, fontWeight: 600, marginBottom: 10, letterSpacing: -0.2, lineHeight: 1.25 }}>
            {flag.ruleName.replaceAll("_", " ").toLowerCase()}
          </div>
          <div style={{ fontSize: 13, color: TOKENS.ink2, lineHeight: 1.6, marginBottom: 18 }}>{flag.rationale}</div>

          <div style={{ fontSize: 10, color: TOKENS.ink4, fontFamily: "'JetBrains Mono', ui-monospace, monospace", letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 6 }}>Evidence</div>
          <div style={{
            background: TOKENS.bg, border: `1px solid ${TOKENS.line}`, borderRadius: 2,
            padding: "10px 12px", marginBottom: 18,
            fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: 12, color: TOKENS.ink2,
            lineHeight: 1.6, whiteSpace: "pre-wrap",
          }}>
            {flag.sourceLocation.spans.map((s, i) => <div key={i}>"{s}"</div>)}
          </div>

          <button onClick={onOpenData} style={{
            width: "100%", background: TOKENS.bg, border: `1px solid ${TOKENS.line}`,
            padding: "8px 12px", fontSize: 11, borderRadius: 2, cursor: "pointer",
            fontFamily: "'JetBrains Mono', ui-monospace, monospace", color: TOKENS.ink2,
            marginBottom: 18, textAlign: "left",
          }}>
            # View extracted fields (21) &rarr;
          </button>

          <div style={{ fontSize: 10, color: TOKENS.ink4, fontFamily: "'JetBrains Mono', ui-monospace, monospace", letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 8 }}>Your decision</div>
          <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
            <ActionButton big active={decision === "CONFIRM"} onClick={() => setDecision("CONFIRM")} variant="confirm">Confirm this flag</ActionButton>
            <ActionButton big active={decision === "OVERRIDE"} onClick={() => setDecision("OVERRIDE")} variant="override">Override</ActionButton>
          </div>
          {decision === "OVERRIDE" && (
            <textarea value={notes || ""} onChange={(e) => setNotes(e.target.value)}
              placeholder="Notes required when overriding a flag..."
              style={{
                width: "100%", minHeight: 80, boxSizing: "border-box",
                border: `1px solid ${TOKENS.line}`, borderRadius: 2,
                padding: 10, fontSize: 13, fontFamily: "inherit", color: TOKENS.ink2,
                background: TOKENS.bg, resize: "vertical",
              }} />
          )}
        </div>

        {/* Stepper footer */}
        <div style={{
          gridColumn: "1 / -1", background: LAYOUT.sidebar, borderTop: `1px solid ${LAYOUT.line}`,
          display: "flex", alignItems: "center", padding: "0 18px", gap: 12,
        }}>
          <button onClick={() => setActiveIdx(Math.max(0, activeIdx - 1))} disabled={activeIdx === 0} style={{
            border: `1px solid ${TOKENS.line}`, background: TOKENS.paper,
            padding: "7px 14px", fontSize: 12, borderRadius: 2,
            cursor: activeIdx === 0 ? "not-allowed" : "pointer",
            color: activeIdx === 0 ? TOKENS.ink4 : TOKENS.ink2, fontFamily: "inherit",
          }}>&larr; Previous</button>
          <div style={{ flex: 1, display: "flex", justifyContent: "center", gap: 6 }}>
            {flags.map((f, i) => (
              <div key={i} onClick={() => setActiveIdx(i)} style={{
                width: 22, height: 6, borderRadius: 3, cursor: "pointer",
                background: i === activeIdx ? LAYOUT.accent : decisions[f.ruleCode]?.decision ? TOKENS.ok : TOKENS.line,
              }} />
            ))}
          </div>
          <button onClick={() => setActiveIdx(Math.min(flags.length - 1, activeIdx + 1))} disabled={activeIdx === flags.length - 1} style={{
            border: "none", background: LAYOUT.accent, color: "#fff",
            padding: "7px 14px", fontSize: 12, borderRadius: 2, fontWeight: 600,
            cursor: activeIdx === flags.length - 1 ? "not-allowed" : "pointer",
            opacity: activeIdx === flags.length - 1 ? 0.5 : 1, fontFamily: "inherit",
          }}>Next flag &rarr;</button>
        </div>
      </div>
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
            <span style={{ fontSize: 10, fontFamily: "'JetBrains Mono', ui-monospace, monospace", color: TOKENS.ink4, letterSpacing: 0.5, textTransform: "uppercase" }}>Extracted fields</span>
            <div style={{ flex: 1 }} />
            <button onClick={onClose} style={{
              border: "none", background: "transparent", cursor: "pointer",
              color: TOKENS.ink3, fontSize: 16, padding: 0, lineHeight: 1,
            }}>&times;</button>
          </div>
          <div style={{ fontSize: 16, fontWeight: 600, color: TOKENS.ink, marginBottom: 4 }}>Bedrock Nova extraction</div>
          <div style={{ fontSize: 11, color: TOKENS.ink4, fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}>
            nova-pro-v1:0 · prompt v1.2 · extracted 2026-04-19 14:24 UTC
          </div>
          {flag && (
            <div style={{
              marginTop: 12, padding: "7px 10px",
              background: TOKENS.highBg, border: `1px solid ${TOKENS.highBgStrong}`,
              borderRadius: 2, fontSize: 11, color: TOKENS.ink2,
              fontFamily: "'JetBrains Mono', ui-monospace, monospace",
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
              {t.label} <span style={{ color: TOKENS.ink4, fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: 11 }}>{t.count}</span>
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
                  fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                  fontSize: 11, color: hi ? TOKENS.ink : TOKENS.ink3, fontWeight: hi ? 600 : 400,
                }}>{row.field}</div>
                <div style={{ fontSize: 12, color: TOKENS.ink2, fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}>{row.value}</div>
                <ConfidenceDot level={row.confidence} />
              </div>
            );
          })}
        </div>

        <div style={{ padding: "12px 22px", borderTop: `1px solid ${TOKENS.line}`, fontSize: 10, color: TOKENS.ink4, fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}>
          21 fields · GET /applications/{"{id}"}/extraction
        </div>
      </div>
    </div>
  );
}

// --- Main review page ---
export function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [app, setApp] = useState<Application | null>(null);
  const [queueApps, setQueueApps] = useState<Application[]>([]);
  const [flags, setFlags] = useState<Flag[]>([]);
  const [extraction, setExtraction] = useState<ExtractionData>({ physical: [], content: [], program: [] });
  const [activeFlagIdx, setActiveFlagIdx] = useState(0);
  const [decisions, setDecisions] = useState<Decisions>({});
  const [currentPage, setCurrentPage] = useState(2);
  const [overallDecision, setOverallDecision] = useState<OverallDecision>(null);
  const [focusMode, setFocusMode] = useState(false);
  const [drawerFlag, setDrawerFlag] = useState<Flag | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [pdfScale, setPdfScale] = useState(1);

  // Keyboard shortcuts
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    // Don't fire when typing in textarea/input
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
      case "f":
        setFocusMode((v) => !v);
        break;
      case "?":
        setShowShortcuts((v) => !v);
        break;
      case "escape":
        setFocusMode(false);
        setDrawerOpen(false);
        setShowShortcuts(false);
        break;
      case "1": case "2": case "3": case "4":
        setCurrentPage(parseInt(e.key));
        break;
    }
  }, [flags, activeFlagIdx]);

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  useEffect(() => {
    if (!id) return;
    setActiveFlagIdx(0);
    setDecisions({});
    setCurrentPage(2);
    setOverallDecision(null);
    setFocusMode(false);
    setDrawerOpen(false);
    getApplication(id).then((data) => {
      setApp(data.application);
      setFlags(data.flags);
      setExtraction(data.extraction);
    });
    listApplications().then(setQueueApps).catch(() => setQueueApps([]));
  }, [id]);

  if (!app) return (
    <div style={{
      width: "100vw", height: "100vh", background: LAYOUT.bg,
      fontFamily: "'Inter', system-ui, sans-serif",
      display: "grid", gridTemplateColumns: "260px 1fr 420px", gridTemplateRows: "44px 1fr",
      overflow: "hidden",
    }}>
      <div style={{ gridColumn: "1 / -1", background: LAYOUT.sidebar, borderBottom: `1px solid ${LAYOUT.line}` }} />
      <div style={{ background: LAYOUT.sidebar, borderRight: `1px solid ${LAYOUT.line}`, padding: 14 }}>
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
      <style>{`@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }`}</style>
    </div>
  );

  const activeFlag = flags[activeFlagIdx];
  const resolvedCount = flags.filter((f) => decisions[f.ruleCode]?.decision).length;
  const allDecided = resolvedCount === flags.length;
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
    const flagDecisions = flags.map((f) => ({
      ruleCode: f.ruleCode,
      decision: decisions[f.ruleCode].decision!,
      notes: decisions[f.ruleCode].notes ?? "",
    }));
    await submitDecision(id, { flagDecisions, overallDecision: overallDecision! });
    setToast(`Decision recorded for ${app.applicantName}.`);
    setTimeout(() => navigate("/dashboard"), 1800);
  };

  // Severity summary for footer
  const highPending = flags.filter((f) => f.severity === "High" && !decisions[f.ruleCode]?.decision).length;
  const medPending = flags.filter((f) => f.severity === "Medium" && !decisions[f.ruleCode]?.decision).length;
  const lowPending = flags.filter((f) => f.severity === "Low" && !decisions[f.ruleCode]?.decision).length;

  return (
    <div style={{
      width: "100vw", height: "100vh", position: "relative",
      background: LAYOUT.bg, fontFamily: "'Inter', system-ui, sans-serif", color: TOKENS.ink,
      display: "grid", gridTemplateColumns: "260px 1fr 420px", gridTemplateRows: "44px 1fr 56px",
      overflow: "hidden",
    }}>
      {/* Top bar */}
      <div style={{
        gridColumn: "1 / -1", borderBottom: `1px solid ${LAYOUT.line}`,
        background: LAYOUT.sidebar, display: "flex", alignItems: "center", padding: "0 18px", gap: 18,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }} onClick={() => navigate("/dashboard")}>
          <div style={{ width: 20, height: 20, borderRadius: 2, background: TOKENS.ink, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 11, fontWeight: 700, fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}>M</div>
          <span style={{ fontSize: 13, fontWeight: 600, letterSpacing: -0.1 }}>MSBN Review</span>
          <span style={{ fontSize: 11, color: TOKENS.ink4, fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}>POC v0.1</span>
        </div>
        <div style={{ height: 20, width: 1, background: LAYOUT.line }} />
        <button onClick={() => navigate("/dashboard")} style={{
          border: `1px solid ${TOKENS.line}`, background: TOKENS.paper,
          padding: "4px 10px", fontSize: 11, borderRadius: 2, cursor: "pointer",
          fontFamily: "'JetBrains Mono', ui-monospace, monospace", color: TOKENS.ink2,
        }}>&larr; Dashboard</button>
        <div style={{ height: 20, width: 1, background: LAYOUT.line }} />
        {flags.length > 0 && <ProgressBar total={flags.length} resolved={resolvedCount} />}
        <div style={{ flex: 1 }} />
        <a href={`https://www.nursys.com`} target="_blank" rel="noopener noreferrer" style={{
          border: `1px solid ${TOKENS.line}`, background: TOKENS.paper,
          color: TOKENS.ink2, padding: "5px 12px", fontSize: 11, borderRadius: 2,
          fontFamily: "'JetBrains Mono', ui-monospace, monospace",
          textDecoration: "none", cursor: "pointer",
        }}>Check Nursys &#8599;</a>
        <button onClick={() => setFocusMode(true)} style={{
          border: `1px solid ${LAYOUT.accent}`, background: TOKENS.paper,
          color: LAYOUT.accent, padding: "5px 12px", fontSize: 11, borderRadius: 2,
          fontFamily: "'JetBrains Mono', ui-monospace, monospace",
          fontWeight: 600, letterSpacing: 0.3, textTransform: "uppercase", cursor: "pointer",
        }}>&#9670; Focus mode</button>
        <button onClick={() => setShowShortcuts(true)} style={{
          border: `1px solid ${TOKENS.line}`, background: TOKENS.paper,
          color: TOKENS.ink3, width: 24, height: 24, fontSize: 13, borderRadius: 2,
          cursor: "pointer", fontFamily: "'JetBrains Mono', ui-monospace, monospace",
          display: "flex", alignItems: "center", justifyContent: "center", padding: 0,
        }} title="Keyboard shortcuts (?)">&quest;</button>
        <div style={{ fontSize: 11, color: TOKENS.ink3, fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}>
          s.pant@msbn.ms.gov · SoD enforced
        </div>
      </div>

      {/* Queue sidebar */}
      <div style={{ borderRight: `1px solid ${LAYOUT.line}`, background: LAYOUT.sidebar, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "12px 14px 10px", borderBottom: `1px solid ${TOKENS.line2}` }}>
          <div style={{ fontSize: 11, color: TOKENS.ink4, fontFamily: "'JetBrains Mono', ui-monospace, monospace", letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 2 }}>Review queue</div>
          <div style={{ fontSize: 13, color: TOKENS.ink2 }}>
            <span style={{ fontWeight: 600 }}>{queueApps.length}</span> pending · sorted by age
          </div>
        </div>
        <div style={{ flex: 1, overflow: "auto" }}>
          {queueApps.map((a) => (
            <QueueRow key={a.applicationId} app={a} active={a.applicationId === id}
              onClick={() => navigate(`/review/${a.applicationId}`)} />
          ))}
        </div>
      </div>

      {/* PDF pane */}
      <div style={{
        background: LAYOUT.pdfBg, overflow: "auto",
        display: "flex", flexDirection: "column", alignItems: "center", padding: "24px 24px 40px", gap: 14,
      }}>
        <div style={{
          width: "100%", maxWidth: 560, display: "flex", alignItems: "center", justifyContent: "space-between",
          fontSize: 11, color: TOKENS.ink3, fontFamily: "'JetBrains Mono', ui-monospace, monospace",
        }}>
          <div>{app.applicantName} · {app.applicationId}</div>
          <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
            {[1, 2, 3, 4].map((p) => (
              <button key={p} onClick={() => setCurrentPage(p)} style={{
                border: `1px solid ${currentPage === p ? TOKENS.ink2 : TOKENS.line}`,
                background: currentPage === p ? TOKENS.ink : TOKENS.paper,
                color: currentPage === p ? "#fff" : TOKENS.ink3,
                width: 24, height: 22, fontSize: 11, cursor: "pointer", borderRadius: 2, fontFamily: "inherit",
              }}>{p}</button>
            ))}
          </div>
        </div>
        <div style={{
          width: Math.round(560 * pdfScale),
          minHeight: Math.round(720 * pdfScale),
          background: TOKENS.paper,
          border: `1px solid ${TOKENS.line}`,
          boxShadow: "0 8px 24px rgba(0,0,0,0.16)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 28,
          boxSizing: "border-box",
          color: TOKENS.ink3,
          fontSize: 13,
          textAlign: "center",
          lineHeight: 1.5,
        }}>
          Transcript page preview is available from processed S3 page images after deployment wiring.
        </div>
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          fontSize: 10, color: TOKENS.ink4, fontFamily: "'JetBrains Mono', ui-monospace, monospace",
        }}>
          <span>source: uploaded transcript · nova-pro-v1:0</span>
          <div style={{ height: 12, width: 1, background: TOKENS.line }} />
          <button onClick={() => setPdfScale((s) => Math.max(0.6, s - 0.1))} style={{
            border: `1px solid ${TOKENS.line}`, background: TOKENS.paper,
            width: 22, height: 20, fontSize: 13, cursor: "pointer", borderRadius: 2,
            color: TOKENS.ink3, fontFamily: "inherit", padding: 0,
          }}>&minus;</button>
          <span>{Math.round(pdfScale * 100)}%</span>
          <button onClick={() => setPdfScale((s) => Math.min(1.5, s + 0.1))} style={{
            border: `1px solid ${TOKENS.line}`, background: TOKENS.paper,
            width: 22, height: 20, fontSize: 13, cursor: "pointer", borderRadius: 2,
            color: TOKENS.ink3, fontFamily: "inherit", padding: 0,
          }}>+</button>
        </div>
      </div>

      {/* Flag list */}
      <div style={{ background: LAYOUT.bg, borderLeft: `1px solid ${LAYOUT.line}`, overflow: "auto", display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "14px 16px", borderBottom: `1px solid ${LAYOUT.line}`, background: LAYOUT.sidebar }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
            <div style={{ fontSize: 15, fontWeight: 600 }}>{app.applicantName}</div>
            <div style={{ fontSize: 11, color: TOKENS.ink4, fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}>#{app.applicationId}</div>
          </div>
          <div style={{ fontSize: 12, color: TOKENS.ink3, marginTop: 3 }}>
            {app.institution} · license {app.licenseNumber}
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
            <Stat label="flags" value={`${flags.length}`} />
            <Stat label="high" value={`${flags.filter((f) => f.severity === "High").length}`} />
            <Stat label="pages" value={`${app.pageCount}`} />
            <Stat label="age" value={timeAgo(app.ageHours)} />
          </div>
        </div>

        <div style={{ flex: 1, overflow: "auto", padding: "12px 14px" }}>
          <div style={{ fontSize: 10, color: TOKENS.ink4, fontFamily: "'JetBrains Mono', ui-monospace, monospace", letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 8 }}>
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
            borderRadius: 2, fontFamily: "'JetBrains Mono', ui-monospace, monospace",
          }}>
            View all extraction fields (21) &rarr;
          </button>
        </div>
      </div>

      {/* Decision footer */}
      <div style={{
        gridColumn: "1 / -1", background: LAYOUT.sidebar, borderTop: `1px solid ${LAYOUT.line}`,
        display: "flex", alignItems: "center", padding: "0 18px", gap: 12,
      }}>
        <div style={{ fontSize: 11, color: TOKENS.ink4, fontFamily: "'JetBrains Mono', ui-monospace, monospace", letterSpacing: 0.5, textTransform: "uppercase" }}>
          Overall decision
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {(["READY_FOR_LICENSING_REVIEW", "RETURN_TO_APPLICANT", "DEFERRED", "DENIED"] as const).map((d) => (
            <button key={d} onClick={() => allDecided && setOverallDecision(d)} disabled={!allDecided}
              style={{
                border: `1px solid ${overallDecision === d ? TOKENS.ink2 : TOKENS.line}`,
                background: overallDecision === d ? (d === "DENIED" ? TOKENS.high : TOKENS.ink) : allDecided ? TOKENS.bg : LAYOUT.sidebar,
                color: overallDecision === d ? "#fff" : allDecided ? TOKENS.ink2 : TOKENS.ink4,
                padding: "6px 11px", fontSize: 11,
                fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                borderRadius: 2, cursor: allDecided ? "pointer" : "not-allowed",
                opacity: allDecided ? 1 : 0.55,
              }}>{d.replaceAll("_", " ").toLowerCase()}</button>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ fontSize: 11, color: canSubmit ? TOKENS.ok : TOKENS.ink4, fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}>
          {!allDecided
            ? <>
                <span style={{ marginRight: 6 }}>{"\u231b"}</span>
                {highPending > 0 && <span style={{ color: TOKENS.high }}>{highPending} High</span>}
                {highPending > 0 && (medPending > 0 || lowPending > 0) && ", "}
                {medPending > 0 && <span style={{ color: TOKENS.med }}>{medPending} Med</span>}
                {medPending > 0 && lowPending > 0 && ", "}
                {lowPending > 0 && <span style={{ color: TOKENS.low }}>{lowPending} Low</span>}
                <span style={{ marginLeft: 4 }}>remaining</span>
              </>
            : !allOverridesNoted
              ? "\u26a0 override note required"
              : !overallDecision
                ? "\u25c7 select a disposition"
                : "\u2713 ready to submit"}
        </div>
        <button disabled={!canSubmit} onClick={handleSubmit} style={{
          background: canSubmit ? TOKENS.ink : TOKENS.line,
          color: "#fff", border: "none",
          padding: "8px 16px", fontSize: 12, fontWeight: 600,
          cursor: canSubmit ? "pointer" : "not-allowed",
          borderRadius: 2, letterSpacing: 0.2,
        }}>
          Submit decision &rarr;
        </button>
      </div>

      {/* Focus mode overlay */}
      {focusMode && flags.length > 0 && (
        <FocusMode flags={flags} activeIdx={activeFlagIdx} setActiveIdx={setActiveFlagIdx}
          decisions={decisions} setDecisions={setDecisions}
          currentPage={currentPage} setCurrentPage={setCurrentPage}
          onClose={() => setFocusMode(false)}
          onOpenData={() => activeFlag && openDrawer(activeFlag)} />
      )}

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
