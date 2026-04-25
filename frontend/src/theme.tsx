import { createContext, useContext } from "react";

export interface Theme {
  name: string;
  bg: string;
  surface: string;
  surfaceAlt: string;
  ink: string;
  ink2: string;
  ink3: string;
  ink4: string;
  line: string;
  line2: string;
  primary: string;
  primaryDark: string;
  primaryInk: string;
  accent: string;
  accentBg: string;
  high: string;
  highBg: string;
  med: string;
  medBg: string;
  low: string;
  lowBg: string;
  ok: string;
  okBg: string;
  serif: string;
  sans: string;
  mono: string;
}

// Modern Government theme — USWDS-influenced, navy + clean white
export const THEME: Theme = {
  name: "Modern Government",
  bg: "#f0f3f7",
  surface: "#ffffff",
  surfaceAlt: "#f5f7fa",
  ink: "#111827",
  ink2: "#374151",
  ink3: "#6b7280",
  ink4: "#9ca3af",
  line: "#e5e7eb",
  line2: "#f3f4f6",
  primary: "#0d2240",
  primaryDark: "#091a33",
  primaryInk: "#ffffff",
  accent: "#005ea2",
  accentBg: "#dbeafe",
  high: "#b91c1c",
  highBg: "#fef2f2",
  med: "#b45309",
  medBg: "#fffbeb",
  low: "#1d4ed8",
  lowBg: "#eff6ff",
  ok: "#15803d",
  okBg: "#f0fdf4",
  serif: "'Montserrat', system-ui, sans-serif",
  sans: "'Open Sans', system-ui, sans-serif",
  mono: "'IBM Plex Mono', ui-monospace, monospace",
};

export const DARK_THEME: Theme = {
  ...THEME,
  name: "Dark Government",
  bg: "#0d1117",
  surface: "#161b22",
  surfaceAlt: "#21262d",
  ink: "#e6edf3",
  ink2: "#c9d1d9",
  ink3: "#8b949e",
  ink4: "#6e7681",
  line: "#30363d",
  line2: "#21262d",
  primary: "#010409",
  primaryDark: "#000000",
  primaryInk: "#e6edf3",
  accent: "#58a6ff",
  accentBg: "#0d2137",
  high: "#f85149",
  highBg: "#2d1215",
  med: "#d29922",
  medBg: "#272115",
  low: "#79c0ff",
  lowBg: "#0d2137",
  ok: "#56d364",
  okBg: "#12261e",
};

export const ThemeCtx = createContext<Theme>(THEME);
export const ThemeModeCtx = createContext<{
  mode: "light" | "dark";
  setMode: (mode: "light" | "dark") => void;
}>({
  mode: "light",
  setMode: () => undefined,
});
export const useT = () => useContext(ThemeCtx);
export const useThemeMode = () => useContext(ThemeModeCtx);
