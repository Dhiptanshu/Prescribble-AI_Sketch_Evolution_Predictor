import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { inkLength } from "@prescribble/engine/pipeline";
import type { Prediction, Stroke } from "@prescribble/engine";
import { ApiError } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useDrawingActions, type Drawing } from "../../lib/drawings";
import { useEngine } from "../../lib/engine";
import { recognisedAt } from "../../lib/recognition";
import type { HistoryPoint } from "./usePredictionLoop";

interface Props {
  mode: "free" | "challenge";
  classes: string[];
  last: Prediction | null;
  history: HistoryPoint[];
  getStrokes: () => Stroke[];
  getDurationMs: () => number | null;
  getInputType?: () => "mouse" | "touch" | "pen" | null;
  /** Changes whenever the drawing changes, so a "saved" confirmation never outlives the drawing it refers to. */
  revision: number;
}

/** Save the current drawing to the signed-in user's gallery, with a label and how early the AI got it. */
export function SavePanel({ mode, classes, last, history, getStrokes, getDurationMs, getInputType, revision }: Props) {
  const { user, backend } = useAuth();
  const { save } = useDrawingActions();
  const engine = useEngine();
  const version = engine.status === "ready" ? engine.version : null;
  const [chosen, setChosen] = useState<string | undefined>();       // undefined = untouched: follow the AI's guess; "" = not sure
  const [saved, setSaved] = useState<Drawing | null>(null);
  const [checked, setChecked] = useState(false);                     // the person says the label is right (never implied by the AI's guess)

  useEffect(() => { setSaved(null); setChosen(undefined); setChecked(false); save.reset(); }, [revision]);   // eslint-disable-line react-hooks/exhaustive-deps

  if (backend !== "online") return null;
  const top = last?.top5[0];

  if (!user) {
    return (
      <section className="card" aria-label="Save">
        <div className="card-head"><h2>Save to gallery</h2></div>
        <p className="meta">Sign in to keep your drawings, see how early the AI recognises them, and share replays.</p>
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <Link className="btn primary" to="/login" state={{ from: "/studio" }}>Sign in</Link>
          <Link className="btn" to="/register" state={{ from: "/studio" }}>Create account</Link>
        </div>
      </section>
    );
  }

  const label = chosen === undefined ? top?.name ?? "" : chosen;
  const error = save.error instanceof ApiError ? save.error.message : save.error ? "Could not reach the server." : null;

  function onSave() {
    const strokes = getStrokes();
    if (!top || !strokes.length || !version) return;
    const idx = label ? classes.indexOf(label) : -1;
    save.mutate(
      {
        strokes, label: label || null, ai_guess: top.name, ai_confidence: top.p,
        recognised_at: label ? recognisedAt(history, idx, inkLength(strokes)) : null,
        mode, duration_ms: getDurationMs(), model_version: version, input_type: getInputType?.() ?? null,
        label_confirmed: !!label && (chosen !== undefined || checked),
      },
      { onSuccess: setSaved },
    );
  }

  return (
    <section className="card" aria-label="Save">
      <div className="card-head"><h2>Save to gallery</h2></div>
      {saved ? (
        <div className="toast good" role="status">
          Saved. <Link to={`/gallery/${saved.id}`}>Open it in your gallery</Link> to replay, share or export it.
        </div>
      ) : (
        <>
          <div className="field">
            <label htmlFor="save-label">What did you draw?</label>
            <select id="save-label" className="input" value={label} disabled={!top} onChange={(e) => { setChosen(e.target.value); setChecked(true); }}>
              <option value="">Not sure</option>
              {classes.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <label className="check"><input type="checkbox" checked={!!label && (chosen !== undefined || checked)} disabled={!label} onChange={(e) => setChecked(e.target.checked)} /> I checked: this label is right</label>
          <p className="meta">Only labels you confirm can help train the model, and only if you allow that in <Link to="/settings">Settings</Link>.</p>
          {error && <div className="toast bad" role="alert" style={{ marginTop: 10 }}>{error}</div>}
          <button className="btn primary" style={{ marginTop: 12 }} onClick={onSave} disabled={!top || save.isPending}>
            {save.isPending ? "Saving…" : "Save drawing"}
          </button>
          {!top && <p className="meta" style={{ marginTop: 8 }}>Draw something first.</p>}
        </>
      )}
    </section>
  );
}
