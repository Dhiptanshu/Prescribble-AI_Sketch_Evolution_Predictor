import { useEffect, useRef } from "react";
import type { Stroke } from "@prescribble/engine/pipeline";
import { paintStrokes } from "../lib/paint";

/** A static, theme-aware preview of a saved drawing. */
export function StrokeThumb({ strokes, label }: { strokes: Stroke[]; label: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const c = ref.current!;
    const paint = () => {
      const dpr = window.devicePixelRatio || 1, size = Math.max(1, Math.round(c.clientWidth * dpr));
      c.width = size; c.height = size;
      paintStrokes(c.getContext("2d")!, strokes, size, Math.max(2, size / 56));
    };
    paint();
    const ro = new ResizeObserver(paint);
    ro.observe(c);
    const mo = new MutationObserver(paint);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => { ro.disconnect(); mo.disconnect(); };
  }, [strokes]);

  return <canvas ref={ref} className="thumb" role="img" aria-label={label} />;
}
