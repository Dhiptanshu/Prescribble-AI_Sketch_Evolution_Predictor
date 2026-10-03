import { describe, expect, it } from "vitest";
import { recognisedAt, type RankPoint } from "./recognition";

const pts = (...tops: number[]): RankPoint[] => tops.map((t, i) => ({ ink: (i + 1) * 20, order: [t, 9, 8, 7, 6] }));   // inks 20, 40, 60, ...

describe("recognisedAt", () => {
  it("is the ink fraction where the label became #1 and stayed #1", () => {
    // guesses: 3, 3, 7, 7, 7   -> label 7 took over at the third point (ink 60 of 100)
    expect(recognisedAt(pts(3, 3, 7, 7, 7), 7, 100)).toBe(0.6);
  });

  it("ignores earlier flickers: only the final unbroken run counts", () => {
    // 7, 3, 7, 7, 7 -> the first 7 was lost again; recognised for good at the third point
    expect(recognisedAt(pts(7, 3, 7, 7, 7), 7, 100)).toBe(0.6);
  });

  it("is null when the final #1 guess is not the label", () => {
    expect(recognisedAt(pts(7, 7, 7, 3), 7, 100)).toBeNull();
    expect(recognisedAt(pts(3, 3, 3), 7, 100)).toBeNull();
  });

  it("is the very first prediction when the AI was right from the start", () => {
    expect(recognisedAt(pts(7, 7, 7), 7, 60)).toBeCloseTo(20 / 60);
  });

  it("handles missing data without inventing a number", () => {
    expect(recognisedAt([], 7, 100)).toBeNull();
    expect(recognisedAt(pts(7), 7, 0)).toBeNull();
    expect(recognisedAt(pts(7), -1, 100)).toBeNull();
  });

  it("never exceeds 1 even if the last sample is slightly past the measured ink", () => {
    expect(recognisedAt([{ ink: 120, order: [7] }], 7, 100)).toBe(1);
  });
});
