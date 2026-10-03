import { afterEach, describe, expect, it } from "vitest";
import { assetsBaseFrom, clampSize, resolveTheme, resolveVersion, toGuesses } from "../src/util";

describe("assetsBaseFrom", () => {
  it("finds the site root from the script's own URL", () => {
    expect(assetsBaseFrom("https://prescribble.example/widget/prescribble-widget.js")).toBe("https://prescribble.example/");
    expect(assetsBaseFrom("http://127.0.0.1:8110/widget/prescribble-widget.js?v=3")).toBe("http://127.0.0.1:8110/");
    expect(assetsBaseFrom("https://cdn.example/apps/prescribble/widget/prescribble-widget.js")).toBe("https://cdn.example/apps/prescribble/");
  });

  it("lets the page override it, normalising the trailing slash", () => {
    expect(assetsBaseFrom("https://a.example/widget/x.js", "https://b.example/pre")).toBe("https://b.example/pre/");
    expect(assetsBaseFrom(null, "/static/")).toBe("/static/");
  });

  it("falls back to the site root when the script URL is unknown", () => {
    expect(assetsBaseFrom(null)).toBe("/");
  });
});

describe("resolveTheme", () => {
  it("follows the visitor's setting only for 'auto'", () => {
    expect(resolveTheme("auto", true)).toBe("dark");
    expect(resolveTheme(undefined, false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });
});

describe("clampSize", () => {
  it("accepts numbers and numeric strings and keeps them in range", () => {
    expect(clampSize(420)).toBe(420);
    expect(clampSize("500")).toBe(500);
    expect(clampSize(50)).toBe(200);
    expect(clampSize("5000")).toBe(800);
  });

  it("falls back for anything that is not a number", () => {
    expect(clampSize(null)).toBe(360);
    expect(clampSize("big")).toBe(360);
    expect(clampSize(undefined, 300)).toBe(300);
  });
});

describe("toGuesses", () => {
  it("renames fields for the public event and rounds probabilities", () => {
    expect(toGuesses([{ name: "house", p: 0.98765 }, { name: "tree", p: 0.00004 }])).toEqual([
      { label: "house", probability: 0.988 }, { label: "tree", probability: 0 },
    ]);
  });
});

describe("resolveVersion", () => {
  const registry = (body: unknown, ok = true) => (async () => ({ ok, json: async () => body })) as unknown as typeof fetch;
  const real = globalThis.fetch;
  afterEach(() => { globalThis.fetch = real; });

  it("uses the version the page asked for without any request", async () => {
    globalThis.fetch = (() => { throw new Error("must not fetch"); }) as unknown as typeof fetch;
    expect(await resolveVersion("https://x.example/", "v7")).toBe("v7");
  });

  it("otherwise follows the live version named in models/registry.json", async () => {
    let asked = "";
    globalThis.fetch = (async (url: string) => { asked = url; return { ok: true, json: async () => ({ active: "v2" }) }; }) as unknown as typeof fetch;
    expect(await resolveVersion("https://x.example/")).toBe("v2");
    expect(asked).toBe("https://x.example/models/registry.json");
  });

  it("falls back to v1 when there is no registry, it is unreadable or it names nothing", async () => {
    globalThis.fetch = registry({}, false);
    expect(await resolveVersion("https://x.example/")).toBe("v1");
    globalThis.fetch = registry({ active: 5 });
    expect(await resolveVersion("https://x.example/")).toBe("v1");
    globalThis.fetch = (async () => { throw new Error("offline"); }) as unknown as typeof fetch;
    expect(await resolveVersion("https://x.example/")).toBe("v1");
  });
});
