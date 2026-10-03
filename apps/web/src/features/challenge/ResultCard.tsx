import { useEffect, useRef } from "react";
import { drawLineChart, seriesColor } from "../../components/charts";
import type { AttemptResult } from "../../lib/challenge";
import { percent } from "../../lib/format";

/** The server's verdict on one attempt, with the AI's confidence in the target as the drawing grew. */
export function ResultCard({ result, target }: { result: AttemptResult; target: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const c = ref.current!;
    const paint = () => drawLineChart(c, [
      { name: `chance it is ${target}`, color: seriesColor(0), bold: true, dots: true, points: result.timeline.map((t) => [t.fraction * 100, t.p_target]) },
      { name: "50% needed", color: "rgba(127,127,160,.6)", points: [[0, 0.5], [100, 0.5]] },
    ], { xMax: 100, xFmt: (v) => `${Math.round(v)}%` });
    paint();
    const ro = new ResizeObserver(paint);
    ro.observe(c);
    const mo = new MutationObserver(paint);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => { ro.disconnect(); mo.disconnect(); };
  }, [result, target]);

  const hit = result.recognised_at != null;
  return (
    <section className="card" aria-label="Result">
      <div className="card-head"><h2>Attempt {result.attempt_no}</h2><span className="meta">verified by the server</span></div>
      <div className="score-row">
        <b className="score gradient-text" aria-label="Score">{result.score}</b>
        <span className="meta">points</span>
      </div>
      <p style={{ margin: "6px 0 12px" }}>
        {hit
          ? <>The AI recognised your <b>{target}</b> once <b>{percent(result.recognised_at!)}</b> of the ink was down{result.confidence_at_hit != null ? ` (${percent(result.confidence_at_hit)} sure)` : ""}.</>
          : <>The AI never settled on <b>{target}</b>. It finished on <b>{result.final_guess}</b> ({percent(result.final_confidence)}).</>}
      </p>
      {!result.counted && (
        <div className="toast bad" role="status" style={{ marginBottom: 12 }}>
          This attempt was not counted on the leaderboard: it was submitted too fast to be a hand-drawn sketch.
        </div>
      )}
      {result.counted && result.rank != null && (
        <p className="meta" style={{ marginBottom: 10 }}>You are <b>#{result.rank}</b> of {result.participants} today · your best: {result.best_score}</p>
      )}
      <canvas ref={ref} className="chart" role="img" aria-label="How sure the AI was that it is the target, as the drawing grew" />
      <div className="legend"><span><i style={{ background: seriesColor(0) }} />chance it is {target}</span><span><i style={{ background: "rgba(127,127,160,.6)" }} />50% needed</span></div>
    </section>
  );
}
