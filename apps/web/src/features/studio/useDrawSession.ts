import { useCallback, useRef, useState } from "react";
import { inkLength } from "@prescribble/engine/pipeline";
import type { Stroke } from "@prescribble/engine";
import type { BoardHandle, BoardPhase } from "../../components/DrawingBoard";
import type { usePredictionLoop } from "./usePredictionLoop";

/**
 * Everything the Studio and the daily Challenge share about "a drawing in progress": the board, live stroke/ink counts, how long
 * the drawing took (first pen-down to last pen-up), a `revision` that changes whenever the user edits, and the live prediction loop.
 */
export function useDrawSession(loop: ReturnType<typeof usePredictionLoop>) {
  const boardRef = useRef<BoardHandle>(null);
  const [meta, setMeta] = useState({ strokes: 0, ink: 0 });
  const [revision, setRevision] = useState(0);
  const timing = useRef<{ start: number | null; end: number | null }>({ start: null, end: null });
  const { run, reset } = loop;

  const onChange = useCallback((strokes: Stroke[], phase: BoardPhase) => {
    setMeta({ strokes: strokes.length, ink: Math.round(inkLength(strokes)) });
    if (phase === "set") return;                                  // scripted playback runs the model itself
    if (phase === "start" && strokes.length === 1) timing.current = { start: performance.now(), end: null };
    if (phase === "end") timing.current.end = performance.now();
    if (phase === "clear") timing.current = { start: null, end: null };
    setRevision((r) => r + 1);
    if (!strokes.length) { reset(); return; }
    void run(strokes, phase === "end" || phase === "undo" || phase === "start");
  }, [run, reset]);

  const getStrokes = useCallback((): Stroke[] => boardRef.current?.strokes() ?? [], []);
  const getDurationMs = useCallback((): number | null => {
    const { start, end } = timing.current;
    return start != null && end != null ? Math.round(end - start) : null;
  }, []);

  const getInputType = useCallback(() => boardRef.current?.inputType() ?? null, []);

  return { boardRef, meta, revision, onChange, getStrokes, getDurationMs, getInputType };
}
