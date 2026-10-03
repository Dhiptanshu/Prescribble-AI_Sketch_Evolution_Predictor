import { afterEach, describe, expect, it } from "vitest";
import { FALLBACK_VERSION, liveVersion } from "./version";

describe("liveVersion", () => {
  const real = globalThis.fetch;
  afterEach(() => { globalThis.fetch = real; });
  const answer = (body: unknown, ok = true) => { globalThis.fetch = (async () => ({ ok, json: async () => body })) as unknown as typeof fetch; };

  it("is the registry's live version, so promoting a model needs no change to the app", async () => {
    answer({ active: "v2", versions: {} });
    expect(await liveVersion("/")).toBe("v2");
  });

  it("asks the server fresh each time (a promotion must be seen on the next load)", async () => {
    let init: RequestInit | undefined;
    globalThis.fetch = (async (_: string, i?: RequestInit) => { init = i; return { ok: true, json: async () => ({ active: "v3" }) }; }) as unknown as typeof fetch;
    await liveVersion("/app/");
    expect(init?.cache).toBe("no-cache");
  });

  it("falls back to the original version when there is no usable registry", async () => {
    answer({}, false);
    expect(await liveVersion("/")).toBe(FALLBACK_VERSION);
    answer({ active: "" });
    expect(await liveVersion("/")).toBe(FALLBACK_VERSION);
    globalThis.fetch = (async () => { throw new Error("offline"); }) as unknown as typeof fetch;
    expect(await liveVersion("/")).toBe(FALLBACK_VERSION);
  });
});
