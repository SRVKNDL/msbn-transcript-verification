import type { Theme } from "./theme";
import type { AuditEvent } from "./types";

export type AuditStage = "created" | "processing" | "flag" | "review" | "system";

export interface AuditStageStyle {
  label: string;
  color: string;
  background: string;
  border: string;
}

export function auditStageForEvent(event: AuditEvent): AuditStage {
  const text = `${event.event} ${event.detail}`.toLowerCase();

  if (/\b(decision|reviewed|reviewer|confirmed|overridden|override|resolved|denied|licensing)\b/.test(text)) {
    return "review";
  }
  if (/\b(flag|rule|safe practice|severity)\b/.test(text)) {
    return "flag";
  }
  if (/\b(created|submitted|uploaded|intake|received)\b/.test(text)) {
    return "created";
  }
  if (/\b(process|processing|extraction|extract|status|queued|queue|classification|ocr|completed|started|began|running)\b/.test(text)) {
    return "processing";
  }
  return "system";
}

export function auditStageStyle(stage: AuditStage, t: Theme): AuditStageStyle {
  switch (stage) {
    case "created":
      return {
        label: "Creation",
        color: t.accent,
        background: t.accentBg,
        border: "rgba(0, 94, 162, 0.3)",
      };
    case "processing":
      return {
        label: "Processing",
        color: t.med,
        background: t.medBg,
        border: "rgba(180, 83, 9, 0.28)",
      };
    case "flag":
      return {
        label: "Flags",
        color: t.high,
        background: t.highBg,
        border: "rgba(185, 28, 28, 0.26)",
      };
    case "review":
      return {
        label: "Review",
        color: t.ok,
        background: t.okBg,
        border: "rgba(21, 128, 61, 0.26)",
      };
    case "system":
      return {
        label: "System",
        color: t.ink3,
        background: t.surfaceAlt,
        border: t.line,
      };
  }
}

export function humanizeAuditEvent(event: string) {
  return event
    .split("_")
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1).toLowerCase()}`)
    .join(" ");
}

export function auditTimeValue(ts: string) {
  const value = new Date(ts).getTime();
  return Number.isFinite(value) ? value : 0;
}

export function formatAuditTimestamp(ts: string) {
  const date = new Date(ts);
  if (!Number.isFinite(date.getTime())) {
    return {
      date: "Unknown date",
      time: "--:--",
      compact: "Unknown time",
    };
  }

  const formattedDate = date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  const formattedTime = date.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });

  return {
    date: formattedDate,
    time: formattedTime,
    compact: `${formattedDate} ${formattedTime}`,
  };
}
