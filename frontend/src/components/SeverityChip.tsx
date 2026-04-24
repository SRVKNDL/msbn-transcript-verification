import { TOKENS } from "../tokens";

const MAP = {
  High: { fg: TOKENS.high, bg: TOKENS.highBg, label: "High" },
  Medium: { fg: TOKENS.med, bg: TOKENS.medBg, label: "Medium" },
  Low: { fg: TOKENS.low, bg: TOKENS.lowBg, label: "Low" },
} as const;

export function SeverityChip({
  severity,
  size = "sm",
}: {
  severity: "High" | "Medium" | "Low" | null;
  size?: "sm" | "lg";
}) {
  if (!severity)
    return (
      <span
        style={{
          fontSize: 11,
          color: TOKENS.ink4,
          fontFamily: "'JetBrains Mono', ui-monospace, monospace",
          letterSpacing: 0.3,
        }}
      >
        clean
      </span>
    );

  const s = MAP[severity];
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
        fontFamily: "'JetBrains Mono', ui-monospace, monospace",
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
