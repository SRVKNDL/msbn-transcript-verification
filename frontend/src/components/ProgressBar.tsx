import { useT } from "../theme";

export function ProgressBar({
  total,
  resolved,
}: {
  total: number;
  resolved: number;
}) {
  const t = useT();
  const pct = Math.round((resolved / total) * 100);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 280 }}>
      <div
        style={{
          fontSize: 10,
          fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
          color: t.ink4,
          letterSpacing: 0.5,
          textTransform: "uppercase",
        }}
      >
        Progress
      </div>
      <div
        style={{
          flex: 1,
          height: 6,
          background: t.line2,
          borderRadius: 3,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${pct}%`,
            background: resolved === total ? t.ok : t.accent,
            transition: "width 200ms ease",
          }}
        />
      </div>
      <div
        style={{
          fontSize: 11,
          fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
          color: t.ink2,
          fontWeight: 600,
          minWidth: 32,
        }}
      >
        {resolved}/{total}
      </div>
    </div>
  );
}
