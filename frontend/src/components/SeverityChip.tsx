import { useT } from "../theme";

export function SeverityChip({
  severity,
  size = "sm",
}: {
  severity: "High" | "Medium" | "Low" | null;
  size?: "sm" | "lg";
}) {
  const t = useT();
  if (!severity)
    return (
      <span
        style={{
          fontSize: 11,
          color: t.ink4,
          fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
          letterSpacing: 0.3,
        }}
      >
        clean
      </span>
    );

  const map = {
    High: { fg: t.high, bg: t.highBg, label: "High" },
    Medium: { fg: t.med, bg: t.medBg, label: "Medium" },
    Low: { fg: t.low, bg: t.lowBg, label: "Low" },
  } as const;
  const s = map[severity];
  const isLg = size === "lg";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        background: s.bg,
        color: s.fg,
        padding: isLg ? "3px 9px" : "2px 7px",
        borderRadius: 3,
        fontSize: isLg ? 12 : 11,
        fontWeight: 600,
        letterSpacing: 0.2,
        fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
        textTransform: "uppercase",
      }}
    >
      <span
        style={{ width: 6, height: 6, borderRadius: 3, background: s.fg }}
      />
      {s.label}
    </span>
  );
}
