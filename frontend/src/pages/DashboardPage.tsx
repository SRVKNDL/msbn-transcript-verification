import { useT } from "../theme";
import { PageHeader, Card, Btn } from "../components/Shell";

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

  const stats = [
    {
      label: "Awaiting review",
      value: "6",
      delta: "+2 today",
      accent: t.accent,
    },
    {
      label: "High-severity flags",
      value: "11",
      delta: "across 4 apps",
      accent: t.high,
    },
    {
      label: "Cleared this week",
      value: "23",
      delta: "+18% vs last",
      accent: t.ok,
    },
    {
      label: "Avg review time",
      value: "12m",
      delta: "target 15m",
      accent: t.ink2,
    },
  ];

  const queue = [
    {
      id: "MSBN-2026-0142",
      name: "Okonkwo, Patricia A.",
      inst: "Western State College of Nursing",
      age: 4,
      flags: [2, 1, 0],
      status: "pending",
    },
    {
      id: "MSBN-2026-0141",
      name: "Delacroix, Marie-Claude",
      inst: "Institut Sup\u00e9rieur des Sciences Infirmi\u00e8res",
      age: 6,
      flags: [1, 2, 1],
      status: "pending",
    },
    {
      id: "MSBN-2026-0140",
      name: "Ramirez, Jose L.",
      inst: "Colegio de Enfermer\u00eda San Rafael",
      age: 9,
      flags: [0, 1, 2],
      status: "pending",
    },
    {
      id: "MSBN-2026-0138",
      name: "Johnson, Kelly R.",
      inst: "Ole Miss School of Nursing",
      age: 26,
      flags: [0, 0, 1],
      status: "pending",
    },
    {
      id: "MSBN-2026-0135",
      name: "Patel, Anaya V.",
      inst: "All India Institute of Medical Sciences",
      age: 48,
      flags: [0, 0, 0],
      status: "clean",
    },
  ];

  const activity = [
    { who: "S. Pant", act: "approved", id: "MSBN-2026-0139", when: 2 },
    {
      who: "S. Pant",
      act: "overrode PHYS_02 on",
      id: "MSBN-2026-0141",
      when: 5,
    },
    {
      who: "System",
      act: "extracted 4 pages for",
      id: "MSBN-2026-0142",
      when: 6,
    },
    { who: "J. Harris", act: "denied", id: "MSBN-2026-0136", when: 23 },
    { who: "System", act: "ingested", id: "MSBN-2026-0142", when: 28 },
  ];

  return (
    <>
      <PageHeader
        eyebrow={`Tuesday \u00b7 21 April 2026 \u00b7 ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} CT`}
        title="Good afternoon, Saurav"
        subtitle="6 applications awaiting review \u00b7 2 flagged as high severity"
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
                    key={r.id}
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
                      {r.id}
                    </td>
                    <td
                      style={{
                        padding: "11px 14px",
                        fontWeight: 500,
                        color: t.ink,
                      }}
                    >
                      {r.name}
                    </td>
                    <td
                      style={{
                        padding: "11px 14px",
                        color: t.ink3,
                        fontSize: 12,
                      }}
                    >
                      {r.inst}
                    </td>
                    <td
                      style={{
                        padding: "11px 14px",
                        color: t.ink3,
                        fontFamily: t.mono,
                        fontSize: 11,
                      }}
                    >
                      {timeAgo(r.age)}
                    </td>
                    <td style={{ padding: "11px 14px" }}>
                      <div style={{ display: "flex", gap: 4 }}>
                        {r.flags[0] > 0 && (
                          <FlagDot n={r.flags[0]} color={t.high} />
                        )}
                        {r.flags[1] > 0 && (
                          <FlagDot n={r.flags[1]} color={t.med} />
                        )}
                        {r.flags[2] > 0 && (
                          <FlagDot n={r.flags[2]} color={t.low} />
                        )}
                        {r.flags.every((f) => f === 0) && (
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
                {activity.map((a, i) => (
                  <div
                    key={i}
                    style={{
                      padding: "11px 18px",
                      borderBottom:
                        i < activity.length - 1
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
                          a.who === "System" ? t.ink4 : t.accent,
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
                        {a.who}
                      </span>{" "}
                      <span style={{ color: t.ink3 }}>{a.act}</span>{" "}
                      <span
                        style={{
                          fontFamily: t.mono,
                          fontSize: 11,
                          color: t.ink2,
                        }}
                      >
                        {a.id}
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
                        {timeAgo(a.when)}
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
