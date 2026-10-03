import { Link, useParams } from "react-router-dom";
import { DrawingPlayer } from "../gallery/DrawingPlayer";
import { ApiError, NetworkError } from "../../lib/api";
import { usePublicDrawing } from "../../lib/drawings";
import { useEngine } from "../../lib/engine";
import { formatDate, recognitionText } from "../../lib/format";

/** Public page for a share link. Anyone can watch the replay; the model runs in the visitor's own browser. */
export function SharedPage() {
  const token = useParams().token ?? "";
  const engine = useEngine();
  const q = usePublicDrawing(token);

  if (q.isLoading) return <p className="empty">Loading…</p>;
  if (q.isError || !q.data) {
    const gone = q.error instanceof ApiError && (q.error.status === 404 || q.error.status === 422);
    const offline = q.error instanceof NetworkError;
    return (
      <div className="auth-wrap card">
        <h1>{gone ? "This drawing is not shared" : offline ? "Needs the server" : "Could not load this drawing"}</h1>
        <p className="sub">{gone ? "The link may have been turned off by its owner." : offline ? "Shared drawings are served by the Prescribble server." : "Try again in a moment."}</p>
        <Link className="btn primary" to="/studio">Open the Studio</Link>
      </div>
    );
  }
  const d = q.data;
  return (
    <div className="studio">
      <section className="card" aria-label="Shared replay">
        <div className="card-head"><h2>A drawing by {d.author}</h2><span className="meta">{formatDate(d.created_at)}</span></div>
        {engine.status === "ready" ? (
          <DrawingPlayer strokes={d.strokes} model={engine.model} title={`Replay of a ${d.label ?? "drawing"} by ${d.author}`} exportName={`prescribble-${d.label ?? "drawing"}`} />
        ) : engine.status === "loading" ? <p className="empty">Loading the model…</p> : <p className="empty">The model failed to load, so the replay is unavailable.</p>}
      </section>
      <aside className="stack">
        <section className="card">
          <div className="card-head"><h2>What the AI made of it</h2></div>
          <p style={{ fontSize: 20, fontWeight: 700, marginBottom: 6 }}>{d.label ? `Drawn as: ${d.label}` : "Unlabelled drawing"}</p>
          <p className="meta">{recognitionText(d.label, d.recognised_at, d.ai_guess)}</p>
          <p className="meta" style={{ marginTop: 14 }}>Press play to watch the guesses change as the drawing grows. The replay runs the real model right here in your browser.</p>
          <Link className="btn primary" style={{ marginTop: 16 }} to="/studio">Try it yourself</Link>
        </section>
      </aside>
    </div>
  );
}
