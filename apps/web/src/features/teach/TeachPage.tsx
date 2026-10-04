import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { DrawingBoard } from "../../components/DrawingBoard";
import { ApiError } from "../../lib/api";
import { useAuth, useAuthActions } from "../../lib/auth";
import { useDrawingActions } from "../../lib/drawings";
import { useEngine } from "../../lib/engine";
import { useTeachActions, useTeachSummary, type TeachSummary } from "../../lib/teach";
import { useDrawSession } from "../studio/useDrawSession";
import { usePredictionLoop } from "../studio/usePredictionLoop";

function Consent() {
  const { updateProfile } = useAuthActions();
  return (
    <div className="auth-wrap card">
      <h1>Teach the AI</h1>
      <p className="sub">You are asked to draw a word, you draw it, and the drawing becomes a training example that helps the next model version recognise real hand-drawn sketches.</p>
      <ul className="plain">
        <li>Only these teaching drawings and their label (the word you were given) are used. No name, email or account id goes into the training data.</li>
        <li>You can stop and delete everything you contributed at any time, here or in Settings.</li>
        <li>Nothing is used for training unless you allow it. Switch it off in Settings and your drawings leave every later export.</li>
      </ul>
      <button className="btn primary lg" onClick={() => updateProfile.mutate({ consent_training: true })} disabled={updateProfile.isPending}>Allow it and start</button>
    </div>
  );
}

/** One word at a time: the one the model has the fewest examples of. Each drawing is saved with the word as its confirmed label. */
export function TeachPage() {
  const { user } = useAuth();
  const engine = useEngine();
  const model = engine.status === "ready" ? engine.model : null;
  const version = engine.status === "ready" ? engine.version : null;
  const loop = usePredictionLoop(model);
  const session = useDrawSession(loop);
  const { save } = useDrawingActions();
  const { next, withdraw, refresh } = useTeachActions();
  const summary = useTeachSummary();
  const [target, setTarget] = useState<string | null>(null);
  const [live, setLive] = useState<TeachSummary | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const asked = useRef(false);

  const load = useCallback((avoid: string | null) => {
    next.mutate(avoid, {
      onSuccess: (n) => { setTarget(n.target); setLive(n.summary); setProblem(null); session.boardRef.current?.clear(); },
      onError: (e) => setProblem(e instanceof ApiError ? e.message : "Could not reach the server."),
    });
  }, [next, session.boardRef]);

  useEffect(() => { if (user?.consent_training && !asked.current) { asked.current = true; load(null); } }, [user?.consent_training, load]);

  if (!user) return null;
  if (!user.consent_training) return <Consent />;

  const top = loop.last?.top5[0];
  const strokes = session.meta.strokes;

  function onSave() {
    const s = session.getStrokes();
    if (!target || !s.length || !top || !version) return;
    save.mutate(
      { strokes: s, label: target, ai_guess: top.name, ai_confidence: top.p, recognised_at: null, mode: "teach", duration_ms: session.getDurationMs(),
        model_version: version, input_type: session.getInputType(), label_confirmed: true },
      {
        onSuccess: () => { refresh(); load(target); },
        onError: (e) => setProblem(e instanceof ApiError ? e.message : "Could not reach the server."),
      },
    );
  }

  const s = live ?? summary.data ?? null;
  return (
    <div className="studio">
      <section className="card" aria-label="Draw this word">
        <div className="prompt">
          <span className="meta">Please draw</span>
          <h1 className="gradient-text">{target ?? "…"}</h1>
        </div>
        <div className="banner">Draw it the way you normally would, with whatever you are using now (mouse, finger or pen). It does not need to be good.</div>
        <DrawingBoard ref={session.boardRef} onChange={session.onChange} locked={!model || !target || save.isPending} hint={target ? `Draw: ${target}.` : "Choosing a word…"} />
        <div className="toolbar">
          <button className="btn" onClick={() => session.boardRef.current?.undo()} disabled={!strokes}>Undo stroke</button>
          <button className="btn" onClick={() => session.boardRef.current?.clear()} disabled={!strokes}>Clear</button>
          <span className="spacer" />
          <button className="btn" onClick={() => load(target)} disabled={next.isPending}>Skip this word</button>
          <button className="btn primary" onClick={onSave} disabled={!strokes || !top || save.isPending}>{save.isPending ? "Saving…" : "Save and next"}</button>
        </div>
        {problem && <div className="toast bad" role="alert" style={{ marginTop: 10 }}>{problem}</div>}
      </section>

      <aside className="stack">
        <section className="card" aria-label="Your contribution">
          <div className="card-head"><h2>Your contribution</h2></div>
          {s ? (
            <>
              <div className="mini-tiles two">
                <div><b>{s.mine}</b><span>drawings from you</span></div>
                <div><b>{s.classes_covered}{s.classes_total ? ` / ${s.classes_total}` : ""}</b><span>words with examples</span></div>
              </div>
              <p className="meta" style={{ marginTop: 10 }}>{s.ready_total} training-ready drawings in total, for model {s.model_version}. You are always given the word with the fewest examples.</p>
            </>
          ) : <p className="empty">Loading…</p>}
        </section>
        <section className="card" aria-label="Your data">
          <div className="card-head"><h2>Your data</h2></div>
          <p className="meta">Teaching drawings are not shown in your gallery or stats. Allow or stop in <Link to="/settings">Settings</Link>.</p>
          <button className="btn" style={{ marginTop: 10 }} disabled={!s?.mine || withdraw.isPending}
                  onClick={() => { if (window.confirm(`Delete all ${s?.mine} drawings you taught the AI with?`)) withdraw.mutate(undefined, { onSuccess: () => setLive(null) }); }}>
            Delete everything I contributed
          </button>
          {withdraw.data && <p className="meta" role="status" style={{ marginTop: 8 }}>Deleted {withdraw.data.deleted}.</p>}
        </section>
      </aside>
    </div>
  );
}
