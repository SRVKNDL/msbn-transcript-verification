import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useT } from "../theme";
import { PageHeader } from "../components/Shell";
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
  const t = useT();
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
        minHeight: "100%",
        background: t.bg,
        color: t.ink,
        display: "flex",
        flexDirection: "column",
      }}
    >
      <PageHeader
        eyebrow="Review queue"
        title={`${shown.length} applications awaiting review`}
        subtitle="Prioritized transcript applications ready for board review"
        actions={
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
                  border: `1px solid ${filter === k ? t.primary : t.line}`,
                  background: filter === k ? t.primary : t.surface,
                  color: filter === k ? t.primaryInk : t.ink2,
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
            onClick={() => {
              /* placeholder */
            }}
            style={{
              border: "1px solid rgba(255,255,255,0.3)",
              background: "transparent",
              color: t.primaryInk,
              padding: "4px 10px",
              fontSize: 11,
              borderRadius: 2,
              cursor: "pointer",
              fontFamily: "inherit",
            }}
          >
            Assign to me
          </button>
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
              onMouseEnter={(e) => (e.currentTarget.style.background = t.surfaceAlt)}
              onMouseLeave={(e) => (e.currentTarget.style.background = selected.has(app.applicationId) ? t.surfaceAlt : "transparent")}
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
                cursor: "pointer",
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
                  {app.flagCount}
                </span>
                <SeverityChip severity={app.highestSeverity} />
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
                  style={{
                    border: `1px solid ${t.line}`,
                    background: t.surfaceAlt,
                    padding: "4px 10px",
                    fontSize: 11,
                    borderRadius: 2,
                    fontFamily: t.mono,
                    color: t.ink2,
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
