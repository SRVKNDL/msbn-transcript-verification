import { TOKENS, LAYOUT } from "../tokens";

export function ProgressBar({
  total,
  resolved,
}: {
  total: number;
  resolved: number;
}) {
  const pct = Math.round((resolved / total) * 100);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 280 }}>
      <div
        style={{
          fontSize: 10,
          fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
          color: TOKENS.ink4,
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
          background: TOKENS.line2,
          borderRadius: 3,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${pct}%`,
            background: resolved === total ? TOKENS.ok : LAYOUT.accent,
            transition: "width 200ms ease",
          }}
        />
      </div>
      <div
        style={{
          fontSize: 11,
          fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
          color: TOKENS.ink2,
          fontWeight: 600,
          minWidth: 32,
        }}
      >
        {resolved}/{total}
      </div>
    </div>
  );
}
