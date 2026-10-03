import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { DrawingBoard } from "../../components/DrawingBoard";
import { GhostLayer } from "../../components/GhostLayer";
import { GuessPanel } from "../../components/GuessPanel";
import { ApiError } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useChallengeStats, useSubmitAttempt, useToday, type AttemptResult } from "../../lib/challenge";
import { useEngine } from "../../lib/engine";
import { useDrawSession } from "../studio/useDrawSession";
import { usePredictionLoop } from "../studio/usePredictionLoop";
import { Countdown } from "./Countdown";
import { LeaderboardCard } from "./LeaderboardCard";
import { ResultCard } from "./ResultCard";

function MyStats() {
  const q = useChallengeStats(true);
  const s = q.data;
  return (
    <section className="card" aria-label="Your challenge record">
      <div className="card-head"><h2>Your record</h2></div>
      {!s ? <p className="empty">Loading…</p> : !s.played ? (
        <p className="meta">Play your first challenge to start a streak.</p>
      ) : (
        <div className="mini-tiles">
          <div><b>{s.streak.current}</b><span>day streak</span></div>
          <div><b>{s.best_score}</b><span>best score</span></div>
          <div><b>{s.average_best}</b><span>average best</span></div>
          <div><b>{s.played}</b><span>days played</span></div>
        </div>
      )}
    </section>
  );
}

export function ChallengePage() {
  const engine = useEngine();
  const model = engine.status === "ready" ? engine.model : null;
  const loop = usePredictionLoop(model);
  const session = useDrawSession(loop);
  const { user, backend } = useAuth();
  const qc = useQueryClient();
  const today = useToday();
  const submit = useSubmitAttempt();
  const [result, setResult] = useState<AttemptResult | null>(null);

  const newDay = useCallback(() => { setResult(null); void qc.invalidateQueries({ queryKey: ["challenge"] }); }, [qc]);

  if (backend === "offline") {
    return (
      <div className="auth-wrap card">
        <h1>Needs the server</h1>
        <p className="sub">The daily challenge is scored by the Prescribble server, so it is unavailable in offline mode. The Studio works fully.</p>
        <Link className="btn primary" to="/studio">Open the Studio</Link>
      </div>
    );
  }
  if (today.isLoading || backend === "checking") return <p className="empty">Loading today’s word…</p>;
  if (today.isError || !today.data) {
    const down = today.error instanceof ApiError && today.error.code === "model_unavailable";
    return <p className="empty">{down ? "The scoring model is not available on this server right now." : "Could not load today’s challenge. Try again in a moment."}</p>;
  }

  const t = today.data;
  const used = t.me?.attempts_used ?? 0;
  const left = result ? result.attempts_left : t.attempts_max - used;
  const outOfAttempts = !!user && left <= 0;
  const locked = !model || !!result || outOfAttempts;
  const error = submit.error instanceof ApiError ? submit.error.message : submit.error ? "Could not reach the server." : null;

  function onSubmit() {
    const strokes = session.getStrokes();
    if (!strokes.length) return;
    submit.mutate({ strokes, duration_ms: session.getDurationMs() }, { onSuccess: setResult });
  }
  function tryAgain() { setResult(null); submit.reset(); session.boardRef.current?.clear(); }

  return (
    <div className="studio">
      <section className="card" aria-label="Today’s challenge">
        <div className="prompt">
          <span className="meta">Today’s word</span>
          <h1 className="gradient-text">{t.target}</h1>
          <span className="meta">New word in <Countdown seconds={t.seconds_left} onDone={newDay} /></span>
        </div>
        <div className="banner">
          {!user ? <>Practice mode: the AI guesses live as you draw. <Link to="/login" state={{ from: "/challenge" }}>Sign in</Link> to submit a scored attempt.</>
            : outOfAttempts ? <>You have used all {t.attempts_max} attempts today. Come back for a new word.</>
            : <>Draw a <b>{t.target}</b>. The sooner the AI names it, the more points you score.</>}
        </div>
        <DrawingBoard
          ref={session.boardRef} onChange={session.onChange} locked={locked}
          underlay={<GhostLayer prediction={loop.last} enabled />}
          hint={model ? `Draw a ${t.target}. The AI starts guessing after your first stroke.` : "Loading the model…"}
        />
        <div className="toolbar">
          <button className="btn" onClick={() => session.boardRef.current?.undo()} disabled={locked || !session.meta.strokes}>Undo stroke</button>
          <button className="btn" onClick={() => session.boardRef.current?.clear()} disabled={locked || !session.meta.strokes}>Clear</button>
          <span className="spacer" />
          <span className="meta">{session.meta.strokes} stroke{session.meta.strokes === 1 ? "" : "s"} · {session.meta.ink} px ink</span>
        </div>
      </section>

      <aside className="stack">
        <section className="card" aria-label="Your attempt">
          <div className="card-head"><h2>Your attempt</h2><span className="meta" aria-live="polite">{user ? `${Math.max(0, left)} of ${t.attempts_max} left` : "visitor"}</span></div>
          {!user ? (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Link className="btn primary" to="/login" state={{ from: "/challenge" }}>Sign in to play</Link>
              <Link className="btn" to="/register" state={{ from: "/challenge" }}>Create account</Link>
            </div>
          ) : result ? (
            left > 0 ? <button className="btn primary" onClick={tryAgain}>Try again ({left} left)</button>
                     : <p className="meta">That was your last attempt today. Best: <b>{result.best_score ?? 0}</b>.</p>
          ) : outOfAttempts ? (
            <p className="meta">Best today: <b>{t.me?.best_score ?? 0}</b>. {t.me?.attempts.map((a) => `${a.score}${a.counted ? "" : " (not counted)"}`).join(" · ")}</p>
          ) : (
            <>
              <p className="meta" style={{ marginBottom: 10 }}>Your name shows on the public leaderboard. You can hide it in <Link to="/settings">settings</Link>.</p>
              {error && <div className="toast bad" role="alert" style={{ marginBottom: 10 }}>{error}</div>}
              <button className="btn primary" onClick={onSubmit} disabled={!session.meta.strokes || submit.isPending || !model}>
                {submit.isPending ? "Scoring…" : "Submit attempt"}
              </button>
              {!!t.me?.attempts.length && <p className="meta" style={{ marginTop: 10 }}>Earlier today: {t.me.attempts.map((a) => `${a.score}${a.counted ? "" : " (not counted)"}`).join(" · ")}</p>}
            </>
          )}
        </section>

        <section className="card" aria-label="What the AI thinks">
          <div className="card-head"><h2>What the AI thinks</h2><span className="meta">live preview</span></div>
          <GuessPanel prediction={loop.last} truth={t.target} />
        </section>

        {result && <ResultCard result={result} target={t.target} />}
        <LeaderboardCard today={t.day} />
        {user && <MyStats />}
      </aside>
    </div>
  );
}
