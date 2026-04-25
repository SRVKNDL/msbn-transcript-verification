import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useT } from "../theme";
import { SeverityChip } from "../components/SeverityChip";
import { getApplication, getAuditTrail } from "../api";
import type { Application, Flag, AuditEvent } from "../types";

export function ReviewedPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const t = useT();

  const [app, setApp] = useState<Application | null>(null);
  const [flags, setFlags] = useState<Flag[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);

  useEffect(() => {
    if (!id) return;
    getApplication(id).then((data) => {
      setApp(data.application);
      setFlags(data.flags);
    });
    getAuditTrail(id).then(setAuditEvents).catch(() => setAuditEvents([]));
  }, [id]);

  if (!app) return (
    <div style={{
      width: "100vw", height: "100vh", background: t.bg,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontFamily: t.sans, color: t.ink3,
    }}>
      Loading...
    </div>
  );

  // Derive decision info from audit events or application status
  const decisionEvent = auditEvents.find(e => e.event === "DECISION_SUBMITTED" || e.event === "REVIEW_COMPLETE");
  const overallDecision = app.status === "REVIEWED" || app.status === "READY_FOR_LICENSING_REVIEW"
    ? app.status
    : decisionEvent?.detail?.match(/disposition:\s*(\S+)/)?.[1] ?? app.status;

  const decisionColor = {
    READY_FOR_LICENSING_REVIEW: t.ok,
    RETURN_TO_APPLICANT: t.med,
    DEFERRED: t.low,
    DENIED: t.high,
  }[overallDecision] ?? t.ink3;

  const decisionBg = {
    READY_FOR_LICENSING_REVIEW: t.okBg,
    RETURN_TO_APPLICANT: t.medBg,
    DEFERRED: t.lowBg,
    DENIED: t.highBg,
  }[overallDecision] ?? t.surfaceAlt;

  // Derive per-flag decisions from audit events
  const flagDecisionMap: Record<string, { decision: string; notes: string }> = {};
  auditEvents.forEach((ev) => {
    if (ev.event === "FLAG_CONFIRMED" || ev.event === "FLAG_OVERRIDDEN") {
      const ruleMatch = ev.detail?.match(/^(\w+)/);
      if (ruleMatch) {
        flagDecisionMap[ruleMatch[1]] = {
          decision: ev.event === "FLAG_CONFIRMED" ? "CONFIRM" : "OVERRIDE",
          notes: ev.detail?.replace(/^\w+\s*·?\s*/, "") ?? "",
        };
      }
    }
  });

  const reviewer = decisionEvent?.actor ?? "Reviewer";
  const submittedAt = decisionEvent?.ts ?? "";
  const confirmedCount = Object.values(flagDecisionMap).filter(d => d.decision === "CONFIRM").length;
  const overriddenCount = Object.values(flagDecisionMap).filter(d => d.decision === "OVERRIDE").length;

  return (
    <div style={{ minHeight: "100vh", background: t.bg, color: t.ink, fontFamily: t.sans }}>
      {/* Header */}
      <div style={{
        padding: "24px 34px 20px", borderBottom: `1px solid ${t.line}`,
        background: t.surface, display: "flex", alignItems: "center", gap: 16,
      }}>
        <button onClick={() => navigate("/queue")} style={{
          border: `1px solid ${t.line}`, background: t.surfaceAlt,
          padding: "6px 12px", fontSize: 12, borderRadius: 6,
          cursor: "pointer", fontFamily: t.mono, color: t.ink3,
          marginRight: 4,
        }}>&#8592; Back</button>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 11, color: t.accent, letterSpacing: 0.8, textTransform: "uppercase", marginBottom: 4, fontFamily: t.mono, fontWeight: 600 }}>
            Reviewed{submittedAt ? ` · ${new Date(submittedAt).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}` : ""}
          </div>
          <div style={{ fontSize: 22, fontWeight: 700, color: t.ink, fontFamily: t.serif }}>
            {app.applicantName}
          </div>
          <div style={{ fontSize: 13, color: t.ink3, marginTop: 3 }}>
            {app.institution} · {app.country} · {app.applicationId}
          </div>
        </div>

        {/* Overall decision badge */}
        <div style={{
          background: decisionBg, color: decisionColor,
          border: `1px solid ${decisionColor}`,
          padding: "10px 20px", borderRadius: 8,
          fontSize: 12, fontWeight: 700, fontFamily: t.mono,
          textTransform: "uppercase", letterSpacing: 0.5, textAlign: "center",
        }}>
          <div style={{ fontSize: 10, opacity: 0.7, marginBottom: 3, letterSpacing: 0.8 }}>Decision</div>
          {overallDecision.replaceAll("_", " ")}
        </div>
      </div>

      <div style={{ padding: "28px 34px 48px", display: "grid", gridTemplateColumns: "1fr 340px", gap: 24, maxWidth: 1100 }}>

        {/* Left — flags with decisions */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: t.ink, fontFamily: t.serif, marginBottom: 4 }}>
            Flag Review Summary
          </div>

          {flags.length === 0 && (
            <div style={{
              background: t.surface, border: `1px solid ${t.line}`, borderRadius: 8,
              padding: "28px 20px", textAlign: "center", color: t.ink4, fontSize: 13,
            }}>No flags were raised for this transcript.</div>
          )}

          {flags.map((flag) => {
            const fd = flagDecisionMap[flag.ruleCode];
            const confirmed = fd?.decision === "CONFIRM";
            const overridden = fd?.decision === "OVERRIDE";
            return (
              <div key={flag.ruleCode} style={{
                background: t.surface, border: `1px solid ${t.line}`,
                borderLeft: `4px solid ${flag.severity === "High" ? t.high : flag.severity === "Medium" ? t.med : t.low}`,
                borderRadius: 8, padding: "16px 20px",
                boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8, flexWrap: "wrap" }}>
                  <span style={{ fontFamily: t.mono, fontSize: 12, fontWeight: 600, color: t.ink }}>{flag.ruleCode}</span>
                  <SeverityChip severity={flag.severity} />
                  {(confirmed || overridden) && (
                    <span style={{
                      fontSize: 11, fontWeight: 600, fontFamily: t.mono,
                      color: confirmed ? t.high : t.ok,
                      background: confirmed ? t.highBg : t.okBg,
                      border: `1px solid ${confirmed ? t.high : t.ok}`,
                      padding: "2px 8px", borderRadius: 4, letterSpacing: 0.3,
                    }}>
                      {confirmed ? "\u2691 CONFIRMED" : "\u2713 OVERRIDDEN"}
                    </span>
                  )}
                  <span style={{ marginLeft: "auto", fontSize: 11, color: t.ink4, fontFamily: t.mono }}>{flag.safePractice}</span>
                </div>
                <div style={{ fontSize: 13, fontWeight: 500, color: t.ink2, marginBottom: 4, textTransform: "lowercase" }}>
                  {flag.ruleName.replaceAll("_", " ")}
                </div>
                <div style={{ fontSize: 12, color: t.ink3, lineHeight: 1.6 }}>{flag.rationale}</div>
                {fd?.notes && fd.notes.trim() && (
                  <div style={{
                    marginTop: 12, padding: "10px 12px",
                    background: t.okBg, border: `1px solid ${t.ok}`,
                    borderRadius: 6, fontSize: 12, color: t.ink2, fontStyle: "italic",
                  }}>
                    <span style={{ fontStyle: "normal", fontWeight: 600, color: t.ok, marginRight: 6 }}>Override note:</span>
                    {fd.notes}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Right — metadata panel */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Application info */}
          <div style={{
            background: t.surface, border: `1px solid ${t.line}`,
            borderRadius: 8, overflow: "hidden",
            boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
          }}>
            <div style={{ padding: "12px 16px", background: t.surfaceAlt, borderBottom: `1px solid ${t.line}` }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: t.ink, fontFamily: t.serif }}>Application Details</div>
            </div>
            <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
              {[
                ["Application ID", app.applicationId],
                ["License Number", app.licenseNumber],
                ["Program Year", app.programYear],
                ["Pages", String(app.pageCount)],
                ["Country", app.country],
                ["Status", "REVIEWED"],
              ].map(([label, val]) => (
                <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                  <span style={{ fontSize: 11, color: t.ink4, fontFamily: t.mono }}>{label}</span>
                  <span style={{ fontSize: 12, color: label === "Status" ? t.ok : t.ink, fontWeight: label === "Status" ? 600 : 400, fontFamily: t.mono }}>{val}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Review metadata */}
          <div style={{
            background: t.surface, border: `1px solid ${t.line}`,
            borderRadius: 8, overflow: "hidden",
            boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
          }}>
            <div style={{ padding: "12px 16px", background: t.surfaceAlt, borderBottom: `1px solid ${t.line}` }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: t.ink, fontFamily: t.serif }}>Review Metadata</div>
            </div>
            <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
              {[
                ["Reviewer", reviewer],
                ["Submitted", submittedAt ? new Date(submittedAt).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) : "—"],
                ["Flags total", String(flags.length)],
                ["Confirmed", String(confirmedCount)],
                ["Overridden", String(overriddenCount)],
              ].map(([label, val]) => (
                <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                  <span style={{ fontSize: 11, color: t.ink4, fontFamily: t.mono }}>{label}</span>
                  <span style={{ fontSize: 12, color: t.ink, fontFamily: t.mono }}>{val}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Audit trail */}
          <div style={{
            background: t.surface, border: `1px solid ${t.line}`,
            borderRadius: 8, overflow: "hidden",
            boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
          }}>
            <div style={{ padding: "12px 16px", background: t.surfaceAlt, borderBottom: `1px solid ${t.line}` }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: t.ink, fontFamily: t.serif }}>Audit Trail</div>
            </div>
            <div style={{ padding: "8px 0" }}>
              {auditEvents.length === 0 && (
                <div style={{ padding: "20px 16px", textAlign: "center", color: t.ink4, fontSize: 12 }}>
                  No audit events.
                </div>
              )}
              {auditEvents.slice(0, 6).map((ev, i) => (
                <div key={i} style={{ display: "flex", gap: 10, padding: "7px 16px", alignItems: "flex-start" }}>
                  <div style={{
                    width: 6, height: 6, borderRadius: 3, marginTop: 5, flexShrink: 0,
                    background: ev.event === "FLAG_RAISED" ? t.high : ev.event.includes("COMPLETE") ? t.ok : t.low,
                  }} />
                  <div>
                    <div style={{ fontSize: 11, color: t.ink2, fontFamily: t.mono, fontWeight: 500 }}>{ev.event}</div>
                    <div style={{ fontSize: 10, color: t.ink4, fontFamily: t.mono, marginTop: 1 }}>
                      {new Date(ev.ts).toISOString().slice(0, 16).replace("T", " ")} · {ev.detail}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
