// Which model version is live: models/registry.json names it, so promoting a version needs no change to this app.
/** Used only when the site has no models/registry.json (a copy made before the registry existed). */
export const FALLBACK_VERSION = "v1";

/** The live model version, read from models/registry.json: promoting a new version changes it with no change to this app. */
export async function liveVersion(base: string): Promise<string> {
  try {
    const res = await fetch(`${base}models/registry.json`, { cache: "no-cache" });
    const active = res.ok ? ((await res.json()) as { active?: unknown }).active : null;
    return typeof active === "string" && active ? active : FALLBACK_VERSION;
  } catch {
    return FALLBACK_VERSION;
  }
}
