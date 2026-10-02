import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, NetworkError, api } from "./api";

const respond = (status: number, body: unknown, raw = false) =>
  vi.stubGlobal("fetch", vi.fn(async () => new Response(raw ? (body as string) : JSON.stringify(body), { status })));

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("returns parsed JSON on success", async () => {
    respond(200, { id: 1 });
    expect(await api<{ id: number }>("/me")).toEqual({ id: 1 });
  });

  it("returns undefined for 204 No Content", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 204 })));
    expect(await api("/auth/logout", { method: "POST" })).toBeUndefined();
  });

  it("maps the standard error body to ApiError with field errors", async () => {
    respond(422, { error: { code: "validation_error", message: "bad", details: [{ field: "email", message: "invalid" }] } });
    const err = await api("/auth/register", { json: {} }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.fieldErrors()).toEqual({ email: "invalid" });
  });

  it("treats an HTML 404 from a static host as 'backend unavailable'", async () => {
    respond(404, "<html>not found</html>", true);
    await expect(api("/me")).rejects.toBeInstanceOf(NetworkError);
  });

  it("treats a failed fetch as a NetworkError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    await expect(api("/me")).rejects.toBeInstanceOf(NetworkError);
  });

  it("sends JSON bodies with POST by default and includes credentials", async () => {
    const f = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", f);
    await api("/auth/login", { json: { a: 1 } });
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/auth/login");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(init.body).toBe('{"a":1}');
  });
});
