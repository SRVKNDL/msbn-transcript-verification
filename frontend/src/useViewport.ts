import { useEffect, useState } from "react";

function readViewportWidth() {
  if (typeof window === "undefined") return 1280;
  return window.innerWidth;
}

export function useViewport() {
  const [width, setWidth] = useState(readViewportWidth);

  useEffect(() => {
    const handleResize = () => setWidth(readViewportWidth());
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return {
    width,
    isPhone: width < 640,
    isTablet: width < 1024,
    isNarrow: width < 1280,
  };
}
