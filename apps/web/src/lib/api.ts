// Typed fetch wrapper for the Prescribble API. Cookies carry the session (httpOnly), so no tokens live in JS.
export interface ApiErrorBody { error: { code: string; message: string; details?: unknown } }

export class ApiError extends Error {
  constructor(readonly status: number, readonly code: string, message: string, readonly details?: unknown) {
    super(message);
  }
  /** Field-level validation messages, when the server sent them. */
  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    if (Array.isArray(this.details)) for (const d of this.details as { field: string; message: string }[]) out[d.field] = d.message;
    return out;
  }
}

/** Thrown when the API cannot be reached at all (offline, or a static build with no backend). */
export class NetworkError extends Error {}

const BASE = "/api/v1";

export async function api<T = void>(path: string, opts: { method?: string; json?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, {
      method: opts.method ?? (opts.json !== undefined ? "POST" : "GET"),
      headers: opts.json !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: opts.json !== undefined ? JSON.stringify(opts.json) : undefined,
      credentials: "include",
      signal: opts.signal,
    });
  } catch (e) {
    throw new NetworkError(e instanceof Error ? e.message : "network error");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = null;
  try { data = text ? JSON.parse(text) : null; } catch { /* non-JSON body (e.g. a static host returning index.html) */ }
  if (!res.ok) {
    const body = data as ApiErrorBody | null;
    if (body?.error) throw new ApiError(res.status, body.error.code, body.error.message, body.error.details);
    // A static host without the API answers with HTML or 404: treat it as "backend not available".
    throw new NetworkError(`API unavailable (HTTP ${res.status})`);
  }
  if (data === null) throw new NetworkError("API returned a non-JSON response");
  return data as T;
}
