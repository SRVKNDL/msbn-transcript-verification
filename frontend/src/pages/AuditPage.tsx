import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { TOKENS, LAYOUT } from "../tokens";
import { getAuditTrail } from "../api";
import { MOCK_APPLICATIONS } from "../mock-data";
import type { AuditEvent } from "../types";

export function AuditPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [events, setEvents] = useState<AuditEvent[]>([]);

  const app = MOCK_APPLICATIONS.find((a) => a.applicationId === id);

  useEffect(() => {
    if (!id) return;
    getAuditTrail(id).then(setEvents);
  }, [id]);

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
      {/* Header */}
      <div
        style={{
          padding: "18px 24px",
          background: LAYOUT.sidebar,
          borderBottom: `1px solid ${LAYOUT.line}`,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 14,
            marginBottom: 10,
          }}
        >
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
            &larr; back to dashboard
          </button>
        </div>
        <div
          style={{
            fontSize: 11,
            color: TOKENS.ink4,
            letterSpacing: 0.5,
            textTransform: "uppercase",
            marginBottom: 4,
          }}
        >
          Audit trail — SP-9
        </div>
        <div style={{ fontSize: 17, fontWeight: 600 }}>
          {app?.applicantName ?? "Application"} · #{id}
        </div>
        <div style={{ fontSize: 12, color: TOKENS.ink3, marginTop: 2 }}>
          Append-only event log. {events.length} events.
        </div>
      </div>

      {/* Timeline */}
      <div style={{ flex: 1, overflow: "auto", padding: "18px 24px" }}>
        <div
          style={{
            position: "relative",
            paddingLeft: 20,
            maxWidth: 640,
            margin: "0 auto",
          }}
        >
          {/* Vertical line */}
          <div
            style={{
              position: "absolute",
              left: 5,
              top: 4,
              bottom: 4,
              width: 1,
              background: TOKENS.line,
            }}
          />

          {events.map((e, i) => {
            const isFlag = e.event === "FLAG_RAISED";
            const isStatus = e.event === "STATUS_CHANGED";
            const dotColor = isFlag
              ? TOKENS.high
              : isStatus
                ? TOKENS.low
                : TOKENS.ink4;
            return (
              <div key={i} style={{ position: "relative", paddingBottom: 14 }}>
                <div
                  style={{
                    position: "absolute",
                    left: -20,
                    top: 3,
                    width: 11,
                    height: 11,
                    borderRadius: 6,
                    background: TOKENS.paper,
                    border: `2px solid ${dotColor}`,
                  }}
                />
                <div
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    gap: 10,
                    marginBottom: 3,
                  }}
                >
                  <span
                    style={{
                      fontFamily:
                        "'JetBrains Mono', ui-monospace, monospace",
                      fontSize: 11,
                      fontWeight: 600,
                      color: TOKENS.ink2,
                      letterSpacing: 0.2,
                    }}
                  >
                    {e.event}
                  </span>
                  <span
                    style={{
                      fontFamily:
                        "'JetBrains Mono', ui-monospace, monospace",
                      fontSize: 10,
                      color: TOKENS.ink4,
                    }}
                  >
                    {e.actor}
                  </span>
                  <span style={{ flex: 1 }} />
                  <span
                    style={{
                      fontFamily:
                        "'JetBrains Mono', ui-monospace, monospace",
                      fontSize: 10,
                      color: TOKENS.ink4,
                    }}
                  >
                    {new Date(e.ts)
                      .toISOString()
                      .slice(0, 19)
                      .replace("T", " ")}
                  </span>
                </div>
                <div
                  style={{
                    fontSize: 12,
                    color: TOKENS.ink3,
                    lineHeight: 1.5,
                  }}
                >
                  {e.detail}
                </div>
              </div>
            );
          })}

          {/* Pending dot */}
          <div style={{ position: "relative", paddingTop: 6, paddingBottom: 14 }}>
            <div
              style={{
                position: "absolute",
                left: -20,
                top: 9,
                width: 11,
                height: 11,
                borderRadius: 6,
                background: TOKENS.paper,
                border: `2px dashed ${TOKENS.ink5}`,
              }}
            />
            <div
              style={{
                fontSize: 11,
                color: TOKENS.ink4,
                fontStyle: "italic",
              }}
            >
              awaiting reviewer decision...
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
