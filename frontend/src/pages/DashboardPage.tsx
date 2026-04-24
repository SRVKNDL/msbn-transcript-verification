import { useEffect, useState } from "react";
import { useT } from "../theme";
import { PageHeader, Card, Btn } from "../components/Shell";
import { listApplications } from "../api";
import type { Application } from "../types";

function timeAgo(hrs: number) {
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function FlagDot({ n, color }: { n: number; color: string }) {
  const t = useT();
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        minWidth: 20,
        height: 18,
        padding: "0 5px",
        background: color,
        color: "#fff",
        fontSize: 10,
        fontWeight: 700,
        fontFamily: t.mono,
        borderRadius: 2,
        letterSpacing: 0.2,
      }}
    >
      {n}
    </span>
  );
}

function ShortcutBtn({
  label,
  hint,
  onClick,
}: {
  label: string;
  hint: string;
  onClick?: () => void;
}) {
  const t = useT();
  return (
    <button
      onClick={onClick}
      style={{
        background: t.surfaceAlt,
        border: `1px solid ${t.line}`,
        padding: "10px 12px",
        borderRadius: 3,
        textAlign: "left",
        cursor: "pointer",
        fontFamily: "inherit",
        display: "flex",
        alignItems: "center",
        gap: 6,
      }}
    >
      <span
        style={{ flex: 1, fontSize: 12, fontWeight: 500, color: t.ink }}
      >
        {label}
      </span>
      <span style={{ fontFamily: t.mono, fontSize: 10, color: t.ink4 }}>
        {hint}
      </span>
    </button>
  );
}

export function DashboardPage({
  onNavigate,
}: {
  onNavigate: (id: string) => void;
}) {
  const t = useT();
  const [apps, setApps] = useState<Application[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listApplications()
      .then(setApps)
      .catch((err: Error) => setError(err.message));
  }, []);

  const awaiting = apps.filter((a) => a.status === "READY_FOR_REVIEW");
  const highSeverity = awaiting.filter((a) => a.highestSeverity === "High").length;
  const flagged = awaiting.reduce((sum, app) => sum + app.flagCount, 0);
  const queue = awaiting.slice(0, 5);

  const stats = [
    {
      label: "Awaiting review",
      value: String(awaiting.length),
      delta: error ?? "from live API",
      accent: t.accent,
    },
    {
      label: "High-severity flags",
      value: String(highSeverity),
      delta: `across ${awaiting.length} apps`,
      accent: t.high,
    },
    {
      label: "Total open flags",
      value: String(flagged),
      delta: "ready for reviewer action",
      accent: t.ok,
    },
    {
      label: "Newest upload",
      value: awaiting[0] ? timeAgo(awaiting[0].ageHours) : "—",
      delta: "queue age",
      accent: t.ink2,
    },
  ];

  return (
    <>
      <PageHeader
        eyebrow={`Tuesday \u00b7 21 April 2026 \u00b7 ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} CT`}
        title="Reviewer dashboard"
        subtitle={`${awaiting.length} applications awaiting review \u00b7 ${highSeverity} high severity`}
      />

      <div
        style={{
          padding: "22px 34px 40px",
          display: "flex",
          flexDirection: "column",
          gap: 18,
        }}
      >
        {/* Stat cards */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: 14,
          }}
        >
          {stats.map((s) => (
            <div
              key={s.label}
              style={{
                background: t.surface,
                border: `1px solid ${t.line}`,
                borderTop: `3px solid ${s.accent}`,
                padding: "16px 18px",
                borderRadius: 3,
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  color: t.ink3,
                  letterSpacing: 0.4,
                  textTransform: "uppercase",
                  fontFamily: t.mono,
                }}
              >
                {s.label}
              </div>
              <div
                style={{
                  fontSize: 34,
                  fontWeight: 600,
                  fontFamily: t.serif,
                  color: t.ink,
                  marginTop: 4,
                  letterSpacing: -0.5,
                  lineHeight: 1,
                }}
              >
                {s.value}
              </div>
              <div style={{ fontSize: 11, color: t.ink4, marginTop: 8 }}>
                {s.delta}
              </div>
            </div>
          ))}
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1.6fr 1fr",
            gap: 18,
          }}
        >
          {/* Queue preview */}
          <Card
            title="Review queue"
            subtitle="Sorted by intake date \u00b7 oldest first"
            pad={0}
            actions={
              <Btn
                variant="ghost"
                size="sm"
                onClick={() => onNavigate("queue")}
              >
                View all &rarr;
              </Btn>
            }
          >
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: 13,
              }}
            >
              <thead>
                <tr style={{ background: t.surfaceAlt }}>
                  {[
                    "Application",
                    "Applicant",
                    "Institution",
                    "Age",
                    "Flags",
                    "",
                  ].map((h, i) => (
                    <th
                      key={i}
                      style={{
                        textAlign: "left",
                        padding: "9px 14px",
                        fontSize: 10,
                        letterSpacing: 0.5,
                        textTransform: "uppercase",
                        fontWeight: 600,
                        color: t.ink3,
                        fontFamily: t.mono,
                        borderBottom: `1px solid ${t.line}`,
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {queue.map((r, i) => (
                  <tr
                    key={r.applicationId}
                    style={{
                      borderBottom:
                        i < queue.length - 1
                          ? `1px solid ${t.line2}`
                          : "none",
                    }}
                  >
                    <td
                      style={{
                        padding: "11px 14px",
                        fontFamily: t.mono,
                        fontSize: 11,
                        color: t.ink2,
                      }}
                    >
                      {r.applicationId}
                    </td>
                    <td
                      style={{
                        padding: "11px 14px",
                        fontWeight: 500,
                        color: t.ink,
                      }}
                    >
                      {r.applicantName}
                    </td>
                    <td
                      style={{
                        padding: "11px 14px",
                        color: t.ink3,
                        fontSize: 12,
                      }}
                    >
                      {r.institution}
                    </td>
                    <td
                      style={{
                        padding: "11px 14px",
                        color: t.ink3,
                        fontFamily: t.mono,
                        fontSize: 11,
                      }}
                    >
                      {timeAgo(r.ageHours)}
                    </td>
                    <td style={{ padding: "11px 14px" }}>
                      <div style={{ display: "flex", gap: 4 }}>
                        {r.flagCount > 0 && (
                          <FlagDot
                            n={r.flagCount}
                            color={r.highestSeverity === "High" ? t.high : t.med}
                          />
                        )}
                        {r.flagCount === 0 && (
                          <span
                            style={{
                              fontSize: 10,
                              color: t.ok,
                              fontFamily: t.mono,
                              letterSpacing: 0.4,
                              textTransform: "uppercase",
                            }}
                          >
                            &check; clean
                          </span>
                        )}
                      </div>
                    </td>
                    <td
                      style={{ padding: "11px 14px", textAlign: "right" }}
                    >
                      <span
                        style={{
                          color: t.primary,
                          fontSize: 12,
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        Review &rarr;
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          {/* Activity + Shortcuts */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 18,
            }}
          >
            <Card title="Recent activity" subtitle="Last 48 hours" pad={0}>
              <div>
                {queue.map((a, i) => (
                  <div
                    key={a.applicationId}
                    style={{
                      padding: "11px 18px",
                      borderBottom:
                        i < queue.length - 1
                          ? `1px solid ${t.line2}`
                          : "none",
                      display: "flex",
                      gap: 10,
                      alignItems: "flex-start",
                    }}
                  >
                    <div
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: 3,
                        marginTop: 6,
                        background:
                          t.accent,
                      }}
                    />
                    <div
                      style={{
                        flex: 1,
                        fontSize: 12,
                        color: t.ink2,
                        lineHeight: 1.5,
                      }}
                    >
                      <span style={{ fontWeight: 600, color: t.ink }}>
                        System
                      </span>{" "}
                      <span style={{ color: t.ink3 }}>queued</span>{" "}
                      <span
                        style={{
                          fontFamily: t.mono,
                          fontSize: 11,
                          color: t.ink2,
                        }}
                      >
                        {a.applicationId}
                      </span>
                      <div
                        style={{
                          fontSize: 10,
                          color: t.ink4,
                          fontFamily: t.mono,
                          marginTop: 2,
                          letterSpacing: 0.2,
                        }}
                      >
                        {timeAgo(a.ageHours)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            <Card title="Shortcuts" pad={14}>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 8,
                }}
              >
                <ShortcutBtn
                  label="Upload transcript"
                  hint="\u2318U"
                  onClick={() => onNavigate("upload")}
                />
                <ShortcutBtn
                  label="Open queue"
                  hint="\u2318Q"
                  onClick={() => onNavigate("queue")}
                />
                <ShortcutBtn
                  label="Audit log"
                  hint="\u2318L"
                  onClick={() => onNavigate("audit")}
                />
                <ShortcutBtn label="Rule reference" hint="\u2318R" />
              </div>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}
