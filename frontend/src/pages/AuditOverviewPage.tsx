import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useT } from "../theme";
import { PageHeader, Card } from "../components/Shell";
import { MOCK_APPLICATIONS, MOCK_AUDIT_BY_APP } from "../mock-data";
import type { AuditEvent } from "../types";

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
  const isFlag = event.event === "FLAG_RAISED";
  const dotColor = isFlag ? t.high : t.low;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        gap: 10,
        padding: "6px 0",
        fontSize: 12,
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: 4,
          background: dotColor,
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
        {new Date(event.ts).toISOString().slice(0, 19).replace("T", " ")}
      </span>
      <span
        style={{
          fontFamily: t.mono,
          fontSize: 11,
          fontWeight: 600,
          color: t.ink2,
          minWidth: 120,
          flexShrink: 0,
        }}
      >
        {event.event}
      </span>
      <span style={{ color: t.ink3, fontSize: 12 }}>{event.detail}</span>
    </div>
  );
}

export function AuditOverviewPage() {
  const t = useT();
  const navigate = useNavigate();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "flags_only">("all");

  const apps = [...MOCK_APPLICATIONS].sort(
    (a, b) => new Date(b.submittedAt).getTime() - new Date(a.submittedAt).getTime()
  );

  const totalEvents = apps.reduce(
    (sum, app) => sum + (MOCK_AUDIT_BY_APP[app.applicationId]?.length ?? 0),
    0
  );

  return (
    <>
      <PageHeader
        eyebrow="SP-9 \u00b7 Compliance"
        title="Audit log"
        subtitle={`${apps.length} documents \u00b7 ${totalEvents} total events`}
        actions={
          <div style={{ display: "flex", gap: 8 }}>
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value as "all" | "flags_only")}
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
            </select>
          </div>
        }
      />

      <div style={{ padding: "20px 34px 40px", maxWidth: 960 }}>
        {apps.map((app) => {
          const allEvents = MOCK_AUDIT_BY_APP[app.applicationId] ?? [];
          const events =
            filter === "flags_only"
              ? allEvents.filter((e) => e.event === "FLAG_RAISED")
              : allEvents;
          const isExpanded = expandedId === app.applicationId;
          const flagCount = allEvents.filter(
            (e) => e.event === "FLAG_RAISED"
          ).length;

          return (
            <div key={app.applicationId} style={{ marginBottom: 10 }}>
              <Card pad={0}>
                {/* Row header */}
                <div
                  onClick={() =>
                    setExpandedId(isExpanded ? null : app.applicationId)
                  }
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
                      {allEvents.length} events
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
                    {events.length === 0 ? (
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
                          navigate(`/audit/${app.applicationId}`);
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
                          navigate(`/review/${app.applicationId}`);
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
