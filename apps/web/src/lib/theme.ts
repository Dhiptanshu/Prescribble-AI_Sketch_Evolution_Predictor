import { useCallback, useEffect, useState } from "react";

type Theme = "dark" | "light";
const KEY = "prescribble.theme";

function initial(): Theme {
  try { const t = localStorage.getItem(KEY); if (t === "dark" || t === "light") return t; } catch { /* storage can be blocked */ }
  return matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(initial);
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  const toggle = useCallback(() => setTheme((t) => {
    const next = t === "dark" ? "light" : "dark";
    try { localStorage.setItem(KEY, next); } catch { /* ignore */ }
    return next;
  }), []);
  return { theme, toggle };
}
