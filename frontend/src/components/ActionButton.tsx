import { useT } from "../theme";

export function ActionButton({
  children,
  active,
  onClick,
  variant,
  big,
}: {
  children: React.ReactNode;
  active: boolean;
  onClick: (e: React.MouseEvent) => void;
  variant: "confirm" | "override";
  big?: boolean;
}) {
  const t = useT();
  const palette =
    variant === "confirm"
      ? { fg: t.high, bg: t.highBg, bgActive: t.high, fgActive: "#fff" }
      : { fg: t.ink2, bg: t.surfaceAlt, bgActive: t.ink, fgActive: "#fff" };

  return (
    <button
      onClick={onClick}
      style={{
        flex: big ? 1 : undefined,
        border: `${big ? "1.5px" : "1px"} solid ${active ? palette.bgActive : t.line}`,
        background: active ? palette.bgActive : palette.bg,
        color: active ? palette.fgActive : palette.fg,
        padding: big ? "10px 14px" : "5px 10px",
        fontSize: big ? 13 : 11,
        borderRadius: 2,
        fontFamily: big ? "inherit" : "'IBM Plex Mono', ui-monospace, monospace",
        fontWeight: 600,
        letterSpacing: big ? 0.2 : 0.3,
        textTransform: big ? undefined : "uppercase",
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}
