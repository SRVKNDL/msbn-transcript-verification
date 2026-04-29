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

// MSBN public-site palette: white surfaces, board blues, and restrained teal accents.
export const THEME: Theme = {
  name: "MSBN Public Site",
  bg: "#f6f7f8",
  surface: "#ffffff",
  surfaceAlt: "#eff6f5",
  ink: "#2d3d48",
  ink2: "#363636",
  ink3: "#6f6f6c",
  ink4: "#8c8986",
  line: "#d7e2e6",
  line2: "#e9eff1",
  primary: "#376491",
  primaryDark: "#2d557c",
  primaryInk: "#ffffff",
  accent: "#1179f1",
  accentBg: "#e6f2ff",
  high: "#b91c1c",
  highBg: "#fef2f2",
  med: "#8a5a00",
  medBg: "#fff7df",
  low: "#41709a",
  lowBg: "#eaf2f8",
  ok: "#279391",
  okBg: "#eff6f5",
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
