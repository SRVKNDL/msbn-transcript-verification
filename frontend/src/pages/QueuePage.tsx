import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { TOKENS, LAYOUT } from "../tokens";
import { SeverityChip } from "../components/SeverityChip";
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

export function QueuePage() {
  const navigate = useNavigate();
  const [apps, setApps] = useState<Application[]>([]);
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useEffect(() => {
    listApplications().then(setApps);
  }, []);

  const shown = apps.filter((a) => {
    if (filter === "high") return a.highestSeverity === "High";
    if (filter === "clean") return a.flagCount === 0;
    return true;
  });

  return (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        background: LAYOUT.bg,
        fontFamily: "'Inter', system-ui, sans-serif",
        color: TOKENS.ink,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {/* Top bar */}
      <div
        style={{
          padding: "14px 22px",
          background: LAYOUT.sidebar,
          borderBottom: `1px solid ${LAYOUT.line}`,
          display: "flex",
          alignItems: "center",
          gap: 14,
        }}
      >
        <div
          onClick={() => navigate("/dashboard")}
          style={{
            width: 22,
            height: 22,
            borderRadius: 2,
            background: TOKENS.ink,
            color: "#fff",
            fontSize: 12,
            fontWeight: 700,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: "'JetBrains Mono', ui-monospace, monospace",
            cursor: "pointer",
          }}
        >
          M
        </div>
        <div style={{ fontSize: 14, fontWeight: 600 }}>MSBN Review</div>
        <div
          style={{
            fontSize: 11,
            color: TOKENS.ink4,
            fontFamily: "'JetBrains Mono', ui-monospace, monospace",
          }}
        >
          POC v0.1
        </div>
        <div style={{ height: 20, width: 1, background: TOKENS.line }} />
        <button
          onClick={() => navigate("/dashboard")}
          style={{
            border: `1px solid ${TOKENS.line}`,
            background: TOKENS.paper,
            padding: "4px 10px",
            fontSize: 11,
            borderRadius: 2,
            cursor: "pointer",
            fontFamily: "'JetBrains Mono', ui-monospace, monospace",
            color: TOKENS.ink2,
          }}
        >
          &larr; Dashboard
        </button>
        <div style={{ flex: 1 }} />
        <div style={{ fontSize: 12, color: TOKENS.ink3 }}>
          s.pant@msbn.ms.gov
        </div>
      </div>

      {/* Header */}
      <div style={{ padding: "22px 32px 8px" }}>
        <div
          style={{
            fontSize: 11,
            color: TOKENS.ink4,
            letterSpacing: 0.5,
            textTransform: "uppercase",
            marginBottom: 3,
          }}
        >
          Review queue
        </div>
        <div
          style={{
            fontSize: 24,
            fontWeight: 600,
            letterSpacing: -0.3,
            marginBottom: 14,
          }}
        >
          {shown.length} applications awaiting review
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {(
            [
              ["all", "All"],
              ["high", "High severity"],
              ["clean", "No flags"],
            ] as const
          ).map(([k, label]) => (
            <button
              key={k}
              onClick={() => setFilter(k)}
              style={{
                border: `1px solid ${filter === k ? TOKENS.ink2 : TOKENS.line}`,
                background: filter === k ? TOKENS.ink : TOKENS.paper,
                color: filter === k ? "#fff" : TOKENS.ink2,
                padding: "5px 12px",
                fontSize: 12,
                borderRadius: 2,
                fontFamily: "inherit",
                cursor: "pointer",
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Bulk action bar */}
      {selected.size > 0 && (
        <div style={{
          margin: "0 32px", padding: "8px 16px",
          background: LAYOUT.accent, borderRadius: "2px 2px 0 0",
          display: "flex", alignItems: "center", gap: 12,
          color: "#fff", fontSize: 12,
          fontFamily: "'JetBrains Mono', ui-monospace, monospace",
        }}>
          <span>{selected.size} selected</span>
          <button onClick={() => {/* placeholder */}} style={{
            border: "1px solid rgba(255,255,255,0.3)", background: "transparent",
            color: "#fff", padding: "4px 10px", fontSize: 11, borderRadius: 2,
            cursor: "pointer", fontFamily: "inherit",
          }}>Assign to me</button>
          <button onClick={() => setSelected(new Set())} style={{
            border: "none", background: "transparent",
            color: "rgba(255,255,255,0.7)", padding: "4px 10px", fontSize: 11,
            cursor: "pointer", fontFamily: "inherit",
          }}>Clear selection</button>
        </div>
      )}

      {/* Table */}
      <div style={{ flex: 1, overflow: "auto", padding: selected.size > 0 ? "0 32px 32px" : "14px 32px 32px" }}>
        <div
          style={{
            background: LAYOUT.paper,
            border: `1px solid ${LAYOUT.line}`,
            borderRadius: selected.size > 0 ? "0 0 2px 2px" : 2,
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
              borderBottom: `1px solid ${TOKENS.line}`,
              background: TOKENS.line2,
              fontSize: 10,
              color: TOKENS.ink3,
              letterSpacing: 0.5,
              textTransform: "uppercase",
              fontFamily: "'JetBrains Mono', ui-monospace, monospace",
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
            <div style={{
              padding: "48px 24px", textAlign: "center", color: TOKENS.ink4,
            }}>
              <div style={{ fontSize: 28, marginBottom: 8, opacity: 0.4 }}>&#9744;</div>
              <div style={{ fontSize: 14, fontWeight: 500, color: TOKENS.ink3, marginBottom: 4 }}>
                No applications match this filter
              </div>
              <div style={{ fontSize: 12 }}>
                Try a different filter or check back later.
              </div>
            </div>
          )}
          {shown.map((app, i) => (
            <div
              key={app.applicationId}
              onClick={() => navigate(`/review/${app.applicationId}`)}
              onMouseEnter={(e) => (e.currentTarget.style.background = TOKENS.line2)}
              onMouseLeave={(e) => (e.currentTarget.style.background = selected.has(app.applicationId) ? TOKENS.line2 : "transparent")}
              style={{
                display: "grid",
                gridTemplateColumns: "24px 14px 1.4fr 1.2fr 100px 140px 100px 90px",
                gap: 14,
                alignItems: "center",
                padding: "12px 16px",
                borderBottom:
                  i < shown.length - 1
                    ? `1px solid ${TOKENS.line2}`
                    : "none",
                cursor: "pointer",
                fontSize: 13,
                color: TOKENS.ink2,
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
                      ? TOKENS.high
                      : app.highestSeverity === "Medium"
                        ? TOKENS.med
                        : app.highestSeverity === "Low"
                          ? TOKENS.low
                          : TOKENS.ink5,
                }}
              />
              <div>
                <div style={{ fontWeight: 500, color: TOKENS.ink }}>
                  {app.applicantName}
                </div>
                <div
                  style={{
                    fontSize: 11,
                    color: TOKENS.ink4,
                    fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                    marginTop: 1,
                  }}
                >
                  #{app.applicationId}
                </div>
              </div>
              <div style={{ fontSize: 12 }}>
                <div>{app.institution}</div>
                <div style={{ fontSize: 11, color: TOKENS.ink4 }}>
                  {app.country}
                </div>
              </div>
              <div
                style={{
                  fontFamily: "'JetBrains Mono', ui-monospace, monospace",
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
                    fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                    fontSize: 12,
                    minWidth: 12,
                  }}
                >
                  {app.flagCount}
                </span>
                <SeverityChip severity={app.highestSeverity} />
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: TOKENS.ink3,
                  fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                  cursor: "help",
                }}
                title={fullTimestamp(app.ageHours)}
              >
                {timeAgo(app.ageHours)}
              </div>
              <div style={{ textAlign: "right" }}>
                <button
                  style={{
                    border: `1px solid ${TOKENS.line}`,
                    background: TOKENS.bg,
                    padding: "4px 10px",
                    fontSize: 11,
                    borderRadius: 2,
                    fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                    color: TOKENS.ink2,
                    cursor: "pointer",
                  }}
                >
                  open &rarr;
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
