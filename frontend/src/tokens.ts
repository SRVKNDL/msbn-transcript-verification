// Design tokens — single source of truth for the dashboard palette.

export const TOKENS = {
  ink: "#1a1816",
  ink2: "#3a3632",
  ink3: "#6b6660",
  ink4: "#9a948c",
  ink5: "#c7c1b8",
  line: "#d9d3c5",
  line2: "#e5dfd0",
  bg: "#ebe6d8",
  bgAlt: "#dfd9c8",
  paper: "#f6f1e3",
  high: "#b23a2e",
  highBg: "#f7e4e0",
  highBgStrong: "#fad5cf",
  med: "#b87a12",
  medBg: "#f7ecd4",
  low: "#2d6aa8",
  lowBg: "#dde9f5",
  ok: "#3d7a3d",
  okBg: "#dfe9d9",
  marker: "#d7321f",
  markerInk: "#c42612",
} as const;

// Shared layout palette — slate-blue workspace, navy accents, cool paper.
export const LAYOUT = {
  bg: "#d6dde4",
  sidebar: "#c4cdd7",
  paper: "#f1f3f5",
  pdfBg: "#b0bac5",
  accent: "#1f3a5f",
  accentInk: "#142744",
  line: "#aab7c4",
  line2: "#c4cdd7",
  chip: "#aab7c4",
} as const;
