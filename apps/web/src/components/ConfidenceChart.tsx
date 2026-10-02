import { useEffect, useRef } from "react";
import { drawLineChart, seriesColor, type Series } from "./charts";
import type { HistoryPoint } from "../features/studio/usePredictionLoop";

/** Probability of the current top-3 guesses as the drawing grows (x = ink drawn, in frame pixels). */
export function ConfidenceChart({ history, classes }: { history: HistoryPoint[]; classes: string[] }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const last = history[history.length - 1];
  const top = last ? last.order.slice(0, 3) : [];
  const series: Series[] = top.map((c, i) => ({
    name: classes[c] ?? String(c), color: seriesColor(i), bold: i === 0, points: history.map((h) => [h.ink, h.probs[c] ?? 0] as [number, number]),
  }));

  useEffect(() => {
    const c = ref.current!;
    const paint = () => drawLineChart(c, series, { xMax: Math.max(last?.ink ?? 0, 60) });
    paint();
    const ro = new ResizeObserver(paint);
    ro.observe(c);
    const mo = new MutationObserver(paint);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => { ro.disconnect(); mo.disconnect(); };
  });

  return (
    <>
      <canvas ref={ref} className="chart" role="img" aria-label="Confidence of the top guesses as you draw" />
      <div className="legend">{series.map((s) => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}</div>
    </>
  );
}
