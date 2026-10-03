import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../lib/api";
import { shareUrl, useDrawing, useDrawingActions } from "../../lib/drawings";
import { useEngine } from "../../lib/engine";
import { formatDate, percent, recognitionText } from "../../lib/format";
import { DrawingPlayer } from "./DrawingPlayer";

function ShareBox({ id, token }: { id: number; token: string | null }) {
  const { share, unshare } = useDrawingActions();
  const [copied, setCopied] = useState(false);
  const url = token ? shareUrl(token) : "";
  async function copy() {
    try { await navigator.clipboard.writeText(url); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { /* clipboard blocked: the field is selectable */ }
  }
  return (
    <section className="card" aria-label="Sharing">
      <div className="card-head"><h2>Share</h2></div>
      {token ? (
        <>
          <p className="meta" style={{ marginBottom: 8 }}>Anyone with this link can watch the replay. It shows your display name, never your email.</p>
          <input className="input" readOnly value={url} aria-label="Share link" onFocus={(e) => e.currentTarget.select()} />
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <button className="btn primary" onClick={() => void copy()}>{copied ? "Copied" : "Copy link"}</button>
            <button className="btn" onClick={() => unshare.mutate(id)} disabled={unshare.isPending}>Stop sharing</button>
          </div>
        </>
      ) : (
        <>
          <p className="meta" style={{ marginBottom: 10 }}>This drawing is private. Create a link to let anyone watch its replay.</p>
          <button className="btn primary" onClick={() => share.mutate(id)} disabled={share.isPending}>Create share link</button>
        </>
      )}
    </section>
  );
}

export function DrawingPage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const engine = useEngine();
  const q = useDrawing(id);
  const { relabel, remove } = useDrawingActions();
  const [confirming, setConfirming] = useState(false);

  if (q.isLoading) return <p className="empty">Loading…</p>;
  if (q.isError || !q.data) {
    const missing = q.error instanceof ApiError && q.error.status === 404;
    return (
      <div className="auth-wrap card">
        <h1>{missing ? "Drawing not found" : "Could not load this drawing"}</h1>
        <p className="sub">{missing ? "It may have been deleted." : "Check your connection and try again."}</p>
        <Link className="btn primary" to="/gallery">Back to your gallery</Link>
      </div>
    );
  }
  const d = q.data;
  const classes = engine.status === "ready" ? engine.model.classes : [];

  return (
    <div className="studio">
      <section className="card" aria-label="Replay">
        <div className="card-head"><h2>Replay</h2><Link to="/gallery" className="meta">← Gallery</Link></div>
        {engine.status === "ready" ? (
          <DrawingPlayer strokes={d.strokes} model={engine.model} title={`Replay of your ${d.label ?? "drawing"}`} exportName={`prescribble-${d.label ?? "drawing"}-${d.id}`} />
        ) : engine.status === "loading" ? <p className="empty">Loading the model…</p> : <p className="empty">The model failed to load, so the replay is unavailable.</p>}
      </section>

      <aside className="stack">
        <section className="card" aria-label="Details">
          <div className="card-head"><h2>Details</h2><span className="meta">{formatDate(d.created_at)}</span></div>
          <div className="field">
            <label htmlFor="relabel">What it is</label>
            <select id="relabel" className="input" value={d.label ?? ""} disabled={relabel.isPending}
              onChange={(e) => relabel.mutate({ id: d.id, label: e.target.value || null })}>
              <option value="">Not sure</option>
              {classes.map((c) => <option key={c} value={c}>{c}</option>)}
              {d.label && !classes.includes(d.label) && <option value={d.label}>{d.label}</option>}
            </select>
          </div>
          <dl className="facts">
            <dt>AI</dt><dd>{recognitionText(d.label, d.recognised_at, d.ai_guess)}</dd>
            <dt>Final guess</dt><dd>{d.ai_guess} ({percent(d.ai_confidence)})</dd>
            <dt>Strokes</dt><dd>{d.n_strokes}</dd>
            <dt>Drawing time</dt><dd>{d.duration_ms != null ? `${(d.duration_ms / 1000).toFixed(1)} s` : "n/a"}</dd>
            <dt>Mode</dt><dd>{d.mode === "challenge" ? "AI challenge" : "Free draw"}</dd>
          </dl>
        </section>
        <ShareBox id={d.id} token={d.share_token} />
        <section className="card" aria-label="Delete">
          <div className="card-head"><h2>Delete</h2></div>
          {confirming ? (
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <span className="meta">Delete this drawing for good?</span>
              <button className="btn" style={{ borderColor: "var(--bad)" }} disabled={remove.isPending}
                onClick={() => remove.mutate(d.id, { onSuccess: () => navigate("/gallery", { replace: true }) })}>Yes, delete</button>
              <button className="btn ghost" onClick={() => setConfirming(false)}>Cancel</button>
            </div>
          ) : (
            <button className="btn" onClick={() => setConfirming(true)}>Delete drawing</button>
          )}
        </section>
      </aside>
    </div>
  );
}
