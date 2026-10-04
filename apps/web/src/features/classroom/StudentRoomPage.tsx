import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { DrawingBoard } from "../../components/DrawingBoard";
import { GhostLayer } from "../../components/GhostLayer";
import { GuessPanel } from "../../components/GuessPanel";
import { ApiError } from "../../lib/api";
import { useEngine } from "../../lib/engine";
import { forgetRoomToken, loadRoomToken, submitDrawing } from "../../lib/rooms";
import { useDrawSession } from "../studio/useDrawSession";
import { usePredictionLoop } from "../studio/usePredictionLoop";
import { Roster } from "./Roster";
import { ResultsBoard, TotalsCard } from "./ResultsBoard";
import { RoundClock } from "./RoundClock";
import { useRoomLive } from "./useRoomLive";

function NotInRoom({ id }: { id: number }) {
  useEffect(() => forgetRoomToken(id), [id]);
  return <div className="auth-wrap card"><h1>You are not in this room</h1><p className="sub">The room may be closed or deleted, or this browser has not joined it.</p><Link className="btn primary" to="/join">Join with a code</Link></div>;
}

/** A student's screen: wait in the lobby, draw while the clock runs (the AI guesses live in your browser), then see the scored results. */
export function StudentRoomPage() {
  const id = Number(useParams().id);
  const saved = loadRoomToken(id);
  const token = saved?.token ?? null;
  const { state: s, link, error } = useRoomLive(id, token);

  const engine = useEngine();
  const model = engine.status === "ready" ? engine.model : null;
  const loop = usePredictionLoop(model);
  const session = useDrawSession(loop);
  const [sentRound, setSentRound] = useState<number | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const sending = useRef(false);

  const roundNo = s?.round?.no ?? null;
  const submitted = !!s?.me?.submitted || (roundNo != null && sentRound === roundNo);

  // A new round starts with a clean board.
  useEffect(() => { if (roundNo != null) { session.boardRef.current?.clear(); setProblem(null); } }, [roundNo, session.boardRef]);

  const done = useRef(false);
  done.current = submitted;

  const handIn = useCallback(async () => {
    const strokes = session.getStrokes();
    if (!token || roundNo == null || !strokes.length || sending.current || done.current) return;
    sending.current = true;
    try {
      await submitDrawing(id, token, { strokes, duration_ms: session.getDurationMs() });
      setSentRound(roundNo);
    } catch (e) {
      if (e instanceof ApiError && e.code === "already_submitted") setSentRound(roundNo);
      else setProblem(e instanceof ApiError ? e.message : "Could not reach the server. Your drawing is still on screen; try again.");
    } finally { sending.current = false; }
  }, [id, token, roundNo, session]);

  // When the clock stops (or the teacher ends the round) the drawing goes in automatically.
  const latest = useRef(handIn);
  latest.current = handIn;
  useEffect(() => { if (s?.phase === "collecting" && !submitted) void latest.current(); }, [s?.phase, submitted]);

  if (!token || error?.status === 401 || error?.status === 404) return <NotInRoom id={id} />;
  if (!s) return <p className="empty">Joining the room…</p>;

  const drawing = s.phase === "drawing";
  const locked = !model || !drawing || submitted;

  return (
    <div className="studio">
      <section className="card" aria-label="The round">
        <div className="prompt">
          <span className="meta">{s.room.name} · you are <b>{saved?.nickname}</b></span>
          {s.round && s.phase !== "results" && s.phase !== "closed" ? <h1 className="gradient-text">{s.round.target}</h1> : <h1>{s.phase === "lobby" ? "Waiting for the teacher" : s.phase === "closed" ? "Room closed" : "Round over"}</h1>}
        </div>
        <div className="banner" aria-live="polite">
          {s.phase === "lobby" && "The round starts when your teacher presses start. You can see who else is here."}
          {drawing && !submitted && <>Draw: <b>{s.round?.target}</b>. The sooner the AI names it, the more points you score.</>}
          {drawing && submitted && "Handed in. Scores appear when the round ends."}
          {s.phase === "collecting" && "Time is up. Collecting the last drawings…"}
          {s.phase === "results" && "Results are below."}
          {s.phase === "closed" && "Your teacher closed this room."}
        </div>
        {(drawing || s.phase === "collecting") && s.round && (
          <div className="clock-row">
            <RoundClock seconds={s.round.seconds_left} receivedAt={s.receivedAt} onZero={() => void latest.current()} />
            <span className="meta">{link === "live" ? "connected" : "reconnecting…"}</span>
          </div>
        )}
        <DrawingBoard
          ref={session.boardRef} onChange={session.onChange} locked={locked}
          underlay={<GhostLayer prediction={loop.last} enabled />}
          hint={!model ? "Loading the model…" : drawing ? `Draw: ${s.round?.target}.` : "Wait for the next round."}
        />
        <div className="toolbar">
          <button className="btn" onClick={() => session.boardRef.current?.undo()} disabled={locked || !session.meta.strokes}>Undo stroke</button>
          <button className="btn" onClick={() => session.boardRef.current?.clear()} disabled={locked || !session.meta.strokes}>Clear</button>
          <span className="spacer" />
          <button className="btn primary" onClick={() => void handIn()} disabled={locked || !session.meta.strokes}>Hand in</button>
        </div>
        {problem && <div className="toast bad" role="alert" style={{ marginTop: 10 }}>{problem}</div>}
      </section>

      <aside className="stack">
        <section className="card" aria-label="What the AI thinks">
          <div className="card-head"><h2>What the AI thinks</h2><span className="meta">live, in your browser</span></div>
          <GuessPanel prediction={loop.last} truth={drawing ? s.round?.target : null} />
        </section>
        {s.results && token && <ResultsBoard roomId={id} token={token} results={s.results} />}
        <TotalsCard totals={s.totals} rounds={s.rounds_finished} />
        <Roster members={s.members} phase={s.phase} />
      </aside>
    </div>
  );
}
