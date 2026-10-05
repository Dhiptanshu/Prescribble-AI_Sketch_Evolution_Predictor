import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Prediction, SketchModel, Stroke } from "@prescribble/engine";
import { usePredictionLoop } from "./usePredictionLoop";

const stroke = (len: number): Stroke[] => [[[0, 0], [len, 0]]];

/** A fake model that resolves on demand so we can test scheduling without ONNX. */
function fakeModel() {
  const calls: { n: number; release: () => void }[] = [];
  const model = {
    classes: ["a", "b"],
    predict: (strokes: Stroke[]) => new Promise<Prediction>((resolve) => {
      const n = strokes[0]![1]![0];
      calls.push({ n, release: () => resolve({
        probs: new Float32Array([0.9, 0.1]), ghost: new Float32Array(), img: new Float32Array(), entropy: 0.1, ms: 1,
        top5: [{ idx: 0, name: "a", p: 0.9 }],
      }) });
    }),
  } as unknown as SketchModel;
  return { model, calls };
}

describe("usePredictionLoop", () => {
  it("returns the prediction for the job and records history", async () => {
    const { model, calls } = fakeModel();
    const { result } = renderHook(() => usePredictionLoop(model));
    let p: Promise<Prediction | null>;
    act(() => { p = result.current.run(stroke(50), true); });
    await waitFor(() => expect(calls).toHaveLength(1));
    await act(async () => { calls[0]!.release(); await p; });
    expect(result.current.last?.top5[0]?.name).toBe("a");
    expect(result.current.history).toHaveLength(1);
    expect(result.current.history[0]!.ink).toBe(50);
  });

  it("drops stale queued work: only the latest drawing is predicted next", async () => {
    const { model, calls } = fakeModel();
    const { result } = renderHook(() => usePredictionLoop(model));
    let first!: Promise<Prediction | null>, second!: Promise<Prediction | null>, third!: Promise<Prediction | null>;
    act(() => { first = result.current.run(stroke(10)); });
    await waitFor(() => expect(calls).toHaveLength(1));
    act(() => { second = result.current.run(stroke(20)); third = result.current.run(stroke(30)); });
    expect(await second).toBeNull();                       // superseded by the third
    await act(async () => { calls[0]!.release(); await first; });
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls.map((c) => c.n)).toEqual([10, 30]);       // 20 was never run
    await act(async () => { calls[1]!.release(); await third; });
  });

  it("clears prediction and history for an empty drawing", async () => {
    const { model, calls } = fakeModel();
    const { result } = renderHook(() => usePredictionLoop(model));
    let p!: Promise<Prediction | null>;
    act(() => { p = result.current.run(stroke(40)); });
    await waitFor(() => expect(calls).toHaveLength(1));
    await act(async () => { calls[0]!.release(); await p; });
    await act(async () => { await result.current.run([]); });
    expect(result.current.last).toBeNull();
    expect(result.current.history).toEqual([]);
  });

  it("keeps the exact strokes a prediction was computed from, even if the board keeps drawing", async () => {
    const { model, calls } = fakeModel();
    const { result } = renderHook(() => usePredictionLoop(model));
    const live = stroke(50);                                  // the board's own array: it keeps growing while the model runs
    let p!: Promise<Prediction | null>;
    act(() => { p = result.current.run(live); });
    await waitFor(() => expect(calls).toHaveLength(1));
    live[0]!.push([90, 0]);                                   // the user draws on while the prediction is running
    live.push([[1, 1], [2, 2]]);
    await act(async () => { calls[0]!.release(); await p; });
    expect(result.current.lastInput).toEqual([[[0, 0], [50, 0]]]);
    expect(result.current.lastInput).not.toBe(live);
  });

  it("does nothing without a model", async () => {
    const { result } = renderHook(() => usePredictionLoop(null));
    expect(await result.current.run(stroke(5))).toBeNull();
  });
});
