import { describe, expect, it } from "vitest";
import golden from "./fixtures/golden.json";
import { cutStrokes, inkLength, rdp, toSeq, type Stroke } from "../src/pipeline";

const near = (a: number, b: number, tol: number) => Math.abs(a - b) <= tol;

describe("pipeline matches the Python training pipeline", () => {
  it("cuts strokes at the same fraction of ink", () => {
    for (const c of golden.cases) {
      const cut = cutStrokes(c.full as Stroke[], c.frac);
      expect(near(inkLength(cut), inkLength(c.cut as Stroke[]), 1e-2)).toBe(true);
      expect(cut.length).toBe(c.cut.length);
    }
  });

  it("produces identical sequence features", () => {
    for (const c of golden.cases) {
      const { seq, length } = toSeq(c.cut as Stroke[]);
      expect(length).toBe(c.length);
      let worst = 0;
      seq.forEach((v, i) => { worst = Math.max(worst, Math.abs(v - (c.seq[i] as number))); });
      expect(worst).toBeLessThan(1e-5);
    }
  });

  it("simplifies strokes like Ramer-Douglas-Peucker in Python", () => {
    for (const c of golden.rdp) {
      expect(rdp(c.input as Stroke, 2.0)).toEqual(c.expected);
    }
  });
});

describe("edge cases", () => {
  it("handles an empty drawing and a single dot", () => {
    expect(toSeq([]).length).toBe(1);
    expect(toSeq([[[10, 10]]]).length).toBe(1);
  });

  it("keeps at most 128 points and always the last one", () => {
    const long: Stroke = Array.from({ length: 500 }, (_, i) => [i % 255, (i * 7) % 255]);
    const { seq, length } = toSeq([long]);
    expect(length).toBeLessThanOrEqual(128);
    const last = long[long.length - 1]!;
    expect(near(seq[(length - 1) * 5]!, last[0] / 255, 1e-6)).toBe(true);
  });

  it("cutStrokes(…, 1) returns everything and cutStrokes(…, 0.5) half the ink", () => {
    const s: Stroke[] = [[[0, 0], [100, 0]], [[100, 0], [100, 100]]];
    expect(inkLength(cutStrokes(s, 1))).toBeCloseTo(200);
    expect(inkLength(cutStrokes(s, 0.5))).toBeCloseTo(100);
  });
});
