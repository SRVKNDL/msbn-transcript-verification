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

// Paper + Ink theme with sans-only font pairing (IBM Plex Sans)
export const THEME: Theme = {
  name: "Paper + Ink",
  bg: "#e8e3d7",
  surface: "#f2ede0",
  surfaceAlt: "#ddd7c6",
  ink: "#14120f",
  ink2: "#2e2c28",
  ink3: "#5f5c55",
  ink4: "#938f86",
  line: "#dcd8cf",
  line2: "#e8e4db",
  primary: "#14120f",
  primaryDark: "#000000",
  primaryInk: "#fbf9f4",
  accent: "#8a2a2a",
  accentBg: "#eedbd7",
  high: "#8a2a2a",
  highBg: "#eedbd7",
  med: "#8a6210",
  medBg: "#f0e3c2",
  low: "#2e4e70",
  lowBg: "#d7dfea",
  ok: "#3a6238",
  okBg: "#dde7d2",
  // sans-only font pairing
  serif: "'IBM Plex Sans', system-ui, sans-serif",
  sans: "'IBM Plex Sans', system-ui, sans-serif",
  mono: "'IBM Plex Mono', ui-monospace, monospace",
};

export const ThemeCtx = createContext<Theme>(THEME);
export const useT = () => useContext(ThemeCtx);
