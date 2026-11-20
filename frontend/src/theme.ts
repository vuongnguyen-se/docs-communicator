import { useCallback, useEffect, useState } from "react";

export type Theme = "dark" | "light";
const KEY = "clouddocs-theme";

/** Saved choice first, then the system setting; dark is the default (approved UI-01 direction). */
export function initialTheme(
  saved: string | null = safeGet(),
  prefersLight: boolean = typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: light)").matches,
): Theme {
  if (saved === "dark" || saved === "light") return saved;
  return prefersLight ? "light" : "dark";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "light" ? "#f6f7fb" : "#0f1535");
}

function safeGet(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => initialTheme());
  useEffect(() => applyTheme(theme), [theme]);
  const toggle = useCallback(() => {
    setTheme((t) => {
      const next: Theme = t === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(KEY, next);
      } catch {
        /* private mode: the choice just isn't remembered */
      }
      return next;
    });
  }, []);
  return [theme, toggle];
}

/** The logo and mark files that suit each theme (see public/brand). */
export function brandAssets(theme: Theme): { logo: string; mark: string } {
  return theme === "light"
    ? { logo: "/brand/logo-on-light.svg", mark: "/brand/mark.svg" }
    : { logo: "/brand/logo-on-dark.svg", mark: "/brand/mark-on-dark.svg" };
}
