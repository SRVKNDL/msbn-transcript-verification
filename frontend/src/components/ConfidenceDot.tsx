import { useT } from "../theme";

export function ConfidenceDot({ level }: { level: "high" | "medium" | "low" }) {
  const t = useT();
  const map = {
    high: { color: t.ok, filled: 3, label: "High (>90%)" },
    medium: { color: t.med, filled: 2, label: "Medium (70\u201390%)" },
    low: { color: t.ink4, filled: 1, label: "Low (<70%)" },
  } as const;
  const c = map[level] ?? map.low;
  return (
    <span
      style={{ display: "inline-flex", gap: 2, cursor: "help" }}
      title={`Extraction confidence: ${c.label}\n\nHigh (>90%): Model is very certain about this value\nMedium (70\u201390%): Moderate certainty, review recommended\nLow (<70%): Low certainty, manual verification required`}
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            width: 5,
            height: 5,
            borderRadius: 3,
            background: i < c.filled ? c.color : t.line,
          }}
        />
      ))}
    </span>
  );
}
