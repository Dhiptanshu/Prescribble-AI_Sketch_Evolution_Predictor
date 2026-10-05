import { useCallback, useRef, useState } from "react";
import { inkLength } from "@prescribble/engine/pipeline";
import type { Prediction, SketchModel, Stroke } from "@prescribble/engine";

export interface HistoryPoint { ink: number; probs: Float32Array; order: number[] }

/** An independent copy: the board keeps pushing points onto its live strokes while a prediction is still running. */
const snapshot = (strokes: Stroke[]): Stroke[] => strokes.map((s) => s.map(([x, y]) => [x, y] as [number, number]));

interface Job { strokes: Stroke[]; record: boolean; resolve: (p: Prediction | null) => void }

/**
 * Runs the model on the current drawing. The latest drawing always wins: if the user keeps drawing while a prediction is
 * running, older queued work is dropped (never queues stale frames). `run` resolves with the prediction for that exact job,
 * or null when it was superseded or the canvas is empty.
 */
export function usePredictionLoop(model: SketchModel | null) {
  const [last, setLast] = useState<Prediction | null>(null);
  /** Exactly the strokes `last` was computed from (not whatever the user has drawn since). */
  const [lastInput, setLastInput] = useState<Stroke[] | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const busy = useRef(false);
  const pending = useRef<Job | null>(null);

  const run = useCallback((strokes: Stroke[], record = false): Promise<Prediction | null> => {
    if (!model) return Promise.resolve(null);
    return new Promise((resolve) => {
      pending.current?.resolve(null);               // superseded
      pending.current = { strokes, record, resolve };
      if (busy.current) return;
      busy.current = true;
      void (async () => {
        try {
          while (pending.current) {
            const job = pending.current;
            pending.current = null;
            if (!job.strokes.length) {
              setLast(null); setLastInput(null); setHistory([]); job.resolve(null);
              continue;
            }
            const seen = snapshot(job.strokes);
            const pred = await model.predict(seen);
            if (pred) {
              const ink = inkLength(seen);
              const point: HistoryPoint = { ink, probs: pred.probs, order: pred.top5.map((g) => g.idx) };
              setHistory((h) => {
                const prev = h[h.length - 1];
                return !prev || job.record || ink - prev.ink > 6 ? [...h, point] : [...h.slice(0, -1), point];
              });
            }
            setLast(pred);
            setLastInput(pred ? seen : null);
            job.resolve(pred);
          }
        } finally {
          busy.current = false;
        }
      })();
    });
  }, [model]);

  const reset = useCallback(() => {
    pending.current?.resolve(null);
    pending.current = null;
    setLast(null);
    setLastInput(null);
    setHistory([]);
  }, []);

  return { last, lastInput, history, run, reset };
}
