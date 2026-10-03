// Small pure helpers (unit-tested without a browser model).
export type ThemeOption = "light" | "dark" | "auto";

/** Where models/ and ort/ live: next to the script (…/widget/x.js → …/), unless the page says otherwise. */
export function assetsBaseFrom(scriptSrc: string | null | undefined, override?: string): string {
  if (override) return override.endsWith("/") ? override : `${override}/`;
  if (scriptSrc) return new URL("../", scriptSrc).href;
  return "/";
}

export function resolveTheme(option: ThemeOption | undefined, prefersDark: boolean): "light" | "dark" {
  return option === "light" || option === "dark" ? option : prefersDark ? "dark" : "light";
}

/** A usable CSS size: numbers or numeric strings, clamped to a sensible range. */
export function clampSize(value: unknown, fallback = 360): number {
  const n = typeof value === "string" ? Number.parseFloat(value) : typeof value === "number" ? value : NaN;
  return Number.isFinite(n) ? Math.min(800, Math.max(200, Math.round(n))) : fallback;
}

export interface Guess { label: string; probability: number }

export function toGuesses(top5: { name: string; p: number }[]): Guess[] {
  return top5.map((g) => ({ label: g.name, probability: Math.round(g.p * 1000) / 1000 }));
}

/** The version to load: the one the page asked for, else the live one from models/registry.json, else v1 (a host with no registry). */
export async function resolveVersion(base: string, requested?: string): Promise<string> {
  if (requested) return requested;
  try {
    const res = await fetch(`${base}models/registry.json`, { cache: "no-cache" });
    const active = res.ok ? ((await res.json()) as { active?: unknown }).active : null;
    return typeof active === "string" && active ? active : "v1";
  } catch {
    return "v1";
  }
}
