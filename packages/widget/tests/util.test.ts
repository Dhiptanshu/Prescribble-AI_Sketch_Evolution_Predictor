import { describe, expect, it } from "vitest";
import { assetsBaseFrom, clampSize, resolveTheme, toGuesses } from "../src/util";

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
