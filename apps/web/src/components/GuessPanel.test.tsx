import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Prediction } from "@prescribble/engine";
import { GuessPanel } from "./GuessPanel";

const pred = (top: [string, number][]): Prediction => ({
  probs: new Float32Array(), ghost: new Float32Array(), img: new Float32Array(), entropy: 0.2, ms: 5,
  top5: top.map(([name, p], idx) => ({ idx, name, p })),
});

describe("GuessPanel", () => {
  it("shows a waiting state before any stroke", () => {
    render(<GuessPanel prediction={null} />);
    expect(screen.getByText("Waiting for a stroke")).toBeTruthy();
  });

  it("shows the top guess and rounds percentages", () => {
    render(<GuessPanel prediction={pred([["house", 0.984], ["tree", 0.011], ["cat", 0.003]])} />);
    expect(screen.getAllByText("house").length).toBeGreaterThan(0);
    expect(screen.getAllByText("98%").length).toBeGreaterThan(0);
    expect(screen.getByText("tree")).toBeTruthy();
  });

  it("marks the correct class when the truth is known", () => {
    const { container } = render(<GuessPanel prediction={pred([["house", 0.6], ["tree", 0.3]])} truth="tree" />);
    const marked = container.querySelectorAll("li.truth");
    expect(marked).toHaveLength(1);
    expect(marked[0]!.textContent).toContain("tree");
  });
});
