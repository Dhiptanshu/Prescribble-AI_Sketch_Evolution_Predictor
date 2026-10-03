import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { FRAME } from "@prescribble/engine/pipeline";
import type { Stroke } from "@prescribble/engine";

export type BoardPhase = "start" | "move" | "end" | "clear" | "undo" | "set";

export type InputType = "mouse" | "touch" | "pen";

export interface BoardHandle {
  strokes(): Stroke[];
  /** The pointer that drew the first stroke of the current drawing (null when the board is empty). */
  inputType(): InputType | null;
  set(strokes: Stroke[]): void;
  clear(): void;
  undo(): void;
}

interface Props {
  onChange: (strokes: Stroke[], phase: BoardPhase) => void;
  locked?: boolean;
  /** Rendered between the paper and the user's ink (the ghost layer). */
  underlay?: React.ReactNode;
  hint?: string;
  progress?: number;
}

/** Drawing surface. Strokes live in the model's fixed 0..255 frame regardless of the canvas's on-screen size. */
export const DrawingBoard = forwardRef<BoardHandle, Props>(function DrawingBoard({ onChange, locked, underlay, hint, progress }, ref) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const strokes = useRef<Stroke[]>([]);
  const drawing = useRef(false);
  const input = useRef<InputType | null>(null);
  const cb = useRef(onChange);
  cb.current = onChange;
  const lockedRef = useRef(!!locked);
  lockedRef.current = !!locked;
  const [hasInk, setHasInk] = useState(false);
  const emit = (phase: BoardPhase) => { setHasInk(strokes.current.length > 0); cb.current(strokes.current, phase); };

  const render = useCallback(() => {
    const c = canvas.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    const dpr = window.devicePixelRatio || 1, k = c.width / FRAME;
    ctx.clearRect(0, 0, c.width, c.height);
    ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue("--ink").trim() || "#fff";
    ctx.fillStyle = ctx.strokeStyle;
    ctx.lineWidth = 4.5 * dpr; ctx.lineCap = "round"; ctx.lineJoin = "round";
    for (const s of strokes.current) {
      const first = s[0]!;
      if (s.length === 1) { ctx.beginPath(); ctx.arc(first[0] * k, first[1] * k, 2.25 * dpr, 0, 7); ctx.fill(); continue; }
      ctx.beginPath(); ctx.moveTo(first[0] * k, first[1] * k);
      for (let i = 1; i < s.length; i++) ctx.lineTo(s[i]![0] * k, s[i]![1] * k);
      ctx.stroke();
    }
  }, []);

  useImperativeHandle(ref, () => ({
    strokes: () => strokes.current,
    inputType: () => (strokes.current.length ? input.current : null),
    set: (s) => { strokes.current = s; render(); emit("set"); },
    clear: () => { strokes.current = []; render(); emit("clear"); },
    undo: () => { strokes.current = strokes.current.slice(0, -1); render(); emit("undo"); },
  }), [render]);   // emit only touches refs and a stable setState

  useEffect(() => {
    const c = canvas.current!;
    const fit = () => {
      const dpr = window.devicePixelRatio || 1, r = c.getBoundingClientRect();
      c.width = Math.max(1, Math.round(r.width * dpr)); c.height = Math.max(1, Math.round(r.height * dpr));
      render();
    };
    const ro = new ResizeObserver(fit);
    ro.observe(c.parentElement!);
    const mo = new MutationObserver(render);                    // repaint when the theme (ink colour) changes
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    fit();
    return () => { ro.disconnect(); mo.disconnect(); };
  }, [render]);

  const pos = (e: React.PointerEvent): [number, number] => {
    const r = canvas.current!.getBoundingClientRect();
    const clamp = (v: number) => Math.min(FRAME, Math.max(0, v));
    return [clamp(((e.clientX - r.left) / r.width) * FRAME), clamp(((e.clientY - r.top) / r.height) * FRAME)];
  };

  return (
    <div className="board">
      {underlay}
      <canvas
        ref={canvas}
        className="draw"
        aria-label="Drawing canvas"
        onPointerDown={(e) => {
          if (lockedRef.current) return;
          e.currentTarget.setPointerCapture(e.pointerId);
          drawing.current = true;
          if (!strokes.current.length) input.current = e.pointerType === "mouse" || e.pointerType === "touch" || e.pointerType === "pen" ? e.pointerType : null;
          strokes.current = [...strokes.current, [pos(e)]];
          render(); emit("start");
        }}
        onPointerMove={(e) => {
          if (!drawing.current) return;
          const s = strokes.current[strokes.current.length - 1]!, p = pos(e), q = s[s.length - 1]!;
          if (Math.hypot(p[0] - q[0], p[1] - q[1]) < 0.8) return;
          s.push(p); render(); emit("move");
        }}
        onPointerUp={() => { if (drawing.current) { drawing.current = false; emit("end"); } }}
        onPointerCancel={() => { if (drawing.current) { drawing.current = false; emit("end"); } }}
      />
      {hint !== undefined && <div className={"hint" + (hasInk ? " hide" : "")}>{hint}</div>}
      {progress !== undefined && <div className="progress"><span style={{ width: `${progress * 100}%` }} /></div>}
    </div>
  );
});
