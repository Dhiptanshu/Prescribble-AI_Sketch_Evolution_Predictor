import { describe, expect, it } from "vitest";
import { formatCountdown, previousDay } from "./challenge";

describe("challenge helpers", () => {
  it("formats the countdown as HH:MM:SS and never goes negative", () => {
    expect(formatCountdown(0)).toBe("00:00:00");
    expect(formatCountdown(59)).toBe("00:00:59");
    expect(formatCountdown(3661)).toBe("01:01:01");
    expect(formatCountdown(86399)).toBe("23:59:59");
    expect(formatCountdown(-5)).toBe("00:00:00");
  });

  it("finds the previous UTC day across month and year boundaries", () => {
    expect(previousDay("2026-10-03")).toBe("2026-10-02");
    expect(previousDay("2026-10-01")).toBe("2026-09-30");
    expect(previousDay("2026-01-01")).toBe("2025-12-31");
    expect(previousDay("2024-03-01")).toBe("2024-02-29");
  });
});
