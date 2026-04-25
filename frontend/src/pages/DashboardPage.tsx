import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
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

function hasExtractedSummary(app: Application) {
  return Boolean(app.applicantName.trim() || app.institution.trim());
}

function isReadyForReview(app: Application) {
  return app.status === "READY_FOR_REVIEW" && hasExtractedSummary(app);
}

function isProcessing(app: Application) {
  return app.status === "PROCESSING" || app.status === "INTAKE_COMPLETE";
}

function displayApplicant(app: Application) {
  return app.applicantName || app.originalFilename || "Transcript upload";
}

function displayInstitution(app: Application) {
  if (app.institution) return app.institution;
  if (isProcessing(app)) return "Extraction in progress";
  if (app.status === "FAILED") return "Processing failed";
  return "Pending metadata";
}

function StatusPill({ status }: { status: string }) {
  const t = useT();
  const processing = status === "PROCESSING" || status === "INTAKE_COMPLETE";
  const failed = status === "FAILED";
  const label = processing
    ? "Processing"
    : status === "READY_FOR_REVIEW"
      ? "Ready"
      : status.replaceAll("_", " ").toLowerCase();
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        border: `1px solid ${failed ? t.high : processing ? t.med : t.ok}`,
        background: failed ? t.highBg : processing ? t.medBg : t.okBg,
        color: failed ? t.high : processing ? t.med : t.ok,
        borderRadius: 2,
        padding: "2px 7px",
        fontSize: 10,
        fontWeight: 700,
        fontFamily: t.mono,
        letterSpacing: 0.3,
        textTransform: "uppercase",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );
}

function applicationTarget(app: Application) {
  if (isReadyForReview(app)) return `/review/${app.applicationId}`;
  if (app.status === "FAILED") return `/audit/${app.applicationId}`;
  return null;
}

export function DashboardPage({
  onNavigate,
}: {
  onNavigate: (id: string) => void;
}) {
  const t = useT();
  const navigate = useNavigate();
  const [apps, setApps] = useState<Application[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      listApplications({ limit: 50 })
        .then((items) => {
          if (cancelled) return;
          setApps(items);
          setError(null);
        })
        .catch((err: Error) => {
          if (!cancelled) setError(err.message);
        });
    };
    load();
    const interval = window.setInterval(load, 8000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  const awaiting = apps.filter(isReadyForReview);
  const processing = apps.filter(isProcessing);
  const failed = apps.filter((a) => a.status === "FAILED");
  const highSeverity = awaiting.filter((a) => a.highestSeverity === "High").length;
  const flagged = awaiting.reduce((sum, app) => sum + app.flagCount, 0);
  const queue = [...processing, ...failed, ...awaiting].slice(0, 5);
  const today = new Date();
  const eyebrowDate = today.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });

  const stats = [
    {
      label: "Awaiting review",
      value: String(awaiting.length),
      delta: error ?? "from live API",
      accent: t.accent,
    },
    {
      label: "Processing",
      value: String(processing.length),
      delta: failed.length ? `${failed.length} failed` : "visible after S3 upload",
      accent: processing.length ? t.med : t.ink2,
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
  ];

  return (
    <>
      <PageHeader
        eyebrow={`${eyebrowDate} \u00b7 ${today.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} CT`}
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
          <Card
            title="Transcript activity"
            subtitle="Processing uploads appear before ready-for-review cases"
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
                    "Status",
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
                {queue.length === 0 && (
                  <tr>
                    <td
                      colSpan={7}
                      style={{
                        padding: "34px 18px",
                        textAlign: "center",
                        color: t.ink4,
                        fontSize: 13,
                      }}
                    >
                      No transcript activity yet.
                    </td>
                  </tr>
                )}
                {queue.map((r, i) => {
                  const target = applicationTarget(r);
                  return (
                    <tr
                      key={r.applicationId}
                      onClick={() => target && navigate(target)}
                      onKeyDown={(e) => {
                        if (!target) return;
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          navigate(target);
                        }
                      }}
                      tabIndex={target ? 0 : undefined}
                      aria-label={target ? `Open ${displayApplicant(r)}` : undefined}
                      style={{
                        borderBottom:
                          i < queue.length - 1
                            ? `1px solid ${t.line2}`
                            : "none",
                        cursor: target ? "pointer" : "default",
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
                      {displayApplicant(r)}
                    </td>
                    <td
                      style={{
                        padding: "11px 14px",
                        color: t.ink3,
                        fontSize: 12,
                      }}
                    >
                      {displayInstitution(r)}
                    </td>
                    <td style={{ padding: "11px 14px" }}>
                      <StatusPill status={r.status} />
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
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (target) navigate(target);
                        }}
                        disabled={!target}
                        style={{
                          border: "none",
                          background: "transparent",
                          padding: 0,
                          color: target ? t.primary : t.ink4,
                          fontSize: 12,
                          fontWeight: 600,
                          cursor: target ? "pointer" : "default",
                          fontFamily: "inherit",
                        }}
                      >
                        {isReadyForReview(r) ? "Review \u2192" : r.status === "FAILED" ? "Audit \u2192" : "Waiting"}
                      </button>
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>

          {/* Recent activity */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 18,
            }}
          >
            <Card title="Recent activity" subtitle="Last 48 hours" pad={0}>
              <div>
                {queue.length === 0 && (
                  <div
                    style={{
                      padding: "34px 18px",
                      textAlign: "center",
                      color: t.ink4,
                      fontSize: 13,
                    }}
                  >
                    No recent activity.
                  </div>
                )}
                {queue.map((a, i) => {
                  const target = applicationTarget(a);
                  return (
                  <div
                    key={a.applicationId}
                    onClick={() => target && navigate(target)}
                    onKeyDown={(e) => {
                      if (!target) return;
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        navigate(target);
                      }
                    }}
                    tabIndex={target ? 0 : undefined}
                    aria-label={target ? `Open ${displayApplicant(a)}` : undefined}
                    style={{
                      padding: "11px 18px",
                      borderBottom:
                        i < queue.length - 1
                          ? `1px solid ${t.line2}`
                          : "none",
                      display: "flex",
                      gap: 10,
                      alignItems: "flex-start",
                      cursor: target ? "pointer" : "default",
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
                      <span style={{ color: t.ink3 }}>
                        {isProcessing(a)
                          ? "started processing"
                          : a.status === "FAILED"
                            ? "failed"
                            : "queued"}
                      </span>{" "}
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
                  );
                })}
              </div>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}
