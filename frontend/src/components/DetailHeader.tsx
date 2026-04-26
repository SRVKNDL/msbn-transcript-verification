import type { CSSProperties, ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type { DetailBackState } from "../navigation";
import { useT } from "../theme";

interface DetailHeaderProps {
  backLabel: string;
  backTo: string;
  title: string;
  subtitle?: string;
  eyebrow?: string;
  statusSummary?: ReactNode;
  primaryActions?: ReactNode;
  secondaryActions?: ReactNode;
  compact?: boolean;
  style?: CSSProperties;
}

export function DetailHeader({
  backLabel,
  backTo,
  title,
  subtitle,
  eyebrow,
  statusSummary,
  primaryActions,
  secondaryActions,
  compact = false,
  style,
}: DetailHeaderProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as DetailBackState | null;
  const from = state?.from;
  const effectiveBackLabel = from?.label ?? backLabel;
  const effectiveBackTo = from?.pathname ?? backTo;
  const t = useT();

  return (
    <section
      style={{
        background: t.surface,
        borderBottom: `1px solid ${t.line}`,
        padding: compact ? "14px 16px" : "22px 34px 20px",
        display: "grid",
        gridTemplateColumns: compact ? "minmax(0, 1fr)" : "minmax(0, 1fr) auto",
        gap: compact ? 12 : 18,
        alignItems: "end",
        ...style,
      }}
    >
      <div style={{ minWidth: 0 }}>
        <button
          onClick={() => navigate(effectiveBackTo)}
          style={{
            border: `1px solid ${t.line}`,
            background: t.surfaceAlt,
            color: t.ink3,
            borderRadius: 5,
            padding: compact ? "5px 9px" : "6px 11px",
            cursor: "pointer",
            fontFamily: t.mono,
            fontSize: compact ? 10 : 11,
            fontWeight: 700,
            marginBottom: compact ? 10 : 12,
          }}
        >
          &larr; {effectiveBackLabel}
        </button>
        {eyebrow && (
          <div
            style={{
              fontFamily: t.mono,
              fontSize: compact ? 10 : 11,
              color: t.ink4,
              letterSpacing: 0.8,
              textTransform: "uppercase",
              marginBottom: 5,
              fontWeight: 700,
            }}
          >
            {eyebrow}
          </div>
        )}
        <h1
          style={{
            margin: 0,
            color: t.ink,
            fontFamily: t.serif,
            fontSize: compact ? 16 : 24,
            lineHeight: 1.2,
            letterSpacing: 0,
            overflowWrap: "anywhere",
          }}
        >
          {title}
        </h1>
        {subtitle && (
          <div
            style={{
              marginTop: 5,
              color: t.ink3,
              fontSize: compact ? 12 : 13,
              lineHeight: 1.45,
              overflowWrap: "anywhere",
            }}
          >
            {subtitle}
          </div>
        )}
      </div>

      {(statusSummary || primaryActions || secondaryActions) && (
        <div
          style={{
            display: "flex",
            flexDirection: compact ? "column" : "row",
            alignItems: compact ? "stretch" : "center",
            justifyContent: "flex-end",
            gap: 10,
            flexWrap: compact ? "nowrap" : "wrap",
          }}
        >
          {statusSummary}
          {secondaryActions}
          {primaryActions}
        </div>
      )}
    </section>
  );
}
