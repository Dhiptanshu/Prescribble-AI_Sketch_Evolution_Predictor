import type { Prediction } from "@prescribble/engine";

/** Top-5 guesses with live bars. `truth` marks the correct class when it is known (replay mode). */
export function GuessPanel({ prediction, truth }: { prediction: Prediction | null; truth?: string | null }) {
  const top = prediction?.top5[0];
  return (
    <div>
      <div className="top1" aria-live="polite">
        {top ? (
          <>
            <span className="name gradient-text">{top.name}</span>
            <span className="pct">{Math.round(top.p * 100)}%</span>
          </>
        ) : (
          <span className="label">Waiting for a stroke</span>
        )}
      </div>
      <ol className="bars">
        {Array.from({ length: 5 }, (_, i) => {
          const g = prediction?.top5[i];
          return (
            <li key={i} className={g && truth === g.name ? "truth" : undefined}>
              <span className="nm">{g?.name ?? "–"}</span>
              <div className="track"><div className="fill" style={{ width: g ? `${(g.p * 100).toFixed(1)}%` : "0%" }} /></div>
              <span className="pc">{g ? `${Math.round(g.p * 100)}%` : ""}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
