import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../lib/api";
import { useModelInfo } from "../../lib/platform";
import { useRoomActions } from "../../lib/rooms";
import { Roster } from "./Roster";
import { ResultsBoard, TotalsCard } from "./ResultsBoard";
import { RoundClock } from "./RoundClock";
import { useRoomLive, type LiveState } from "./useRoomLive";

const DURATIONS = [30, 45, 60, 90, 120];

function StartRound({ roomId, round }: { roomId: number; round: number }) {
  const { start } = useRoomActions();
  const model = useModelInfo();
  const [target, setTarget] = useState("");
  const [seconds, setSeconds] = useState(60);
  const error = start.error instanceof ApiError ? start.error.message : start.error ? "Could not reach the server." : null;
  return (
    <section className="card" aria-label="Start a round">
      <div className="card-head"><h2>Round {round}</h2></div>
      <div className="round-form">
        <div className="field">
          <label htmlFor="word">Word</label>
          <select id="word" className="input" value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">Random word</option>
            {[...(model.data?.classes ?? [])].sort().map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="secs">Time</label>
          <select id="secs" className="input" value={seconds} onChange={(e) => setSeconds(Number(e.target.value))}>
            {DURATIONS.map((d) => <option key={d} value={d}>{d} seconds</option>)}
          </select>
        </div>
        <button className="btn primary lg" disabled={start.isPending} onClick={() => start.mutate({ id: roomId, target: target || null, duration_s: seconds })}>
          {start.isPending ? "Starting…" : "Start round"}
        </button>
      </div>
      {error && <div className="toast bad" role="alert" style={{ marginTop: 10 }}>{error}</div>}
    </section>
  );
}

function RunningRound({ roomId, s }: { roomId: number; s: LiveState }) {
  const { end } = useRoomActions();
  const round = s.round!;
  const done = s.members.filter((m) => m.submitted).length;
  return (
    <section className="card" aria-label="Round in progress">
      <div className="prompt">
        <span className="meta">Round {round.no} · word</span>
        <h1 className="gradient-text">{round.target}</h1>
      </div>
      {s.phase === "drawing" ? (
        <div className="clock-row">
          <RoundClock seconds={round.seconds_left} receivedAt={s.receivedAt} />
          <span className="meta" aria-live="polite">{done} of {s.members.length} handed in</span>
          <span className="spacer" />
          <button className="btn" disabled={end.isPending} onClick={() => end.mutate(roomId)}>End round now</button>
        </div>
      ) : <p className="meta" aria-live="polite">Time is up. Collecting the last drawings…</p>}
    </section>
  );
}

/** The teacher's live control room for one classroom. */
export function TeacherRoomPage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const { state: s, link, error } = useRoomLive(id, null);
  const { close, remove } = useRoomActions();

  if (error?.status === 404) return <div className="auth-wrap card"><h1>Room not found</h1><p className="sub">It may have been deleted.</p><Link className="btn primary" to="/classroom">Back to your rooms</Link></div>;
  if (!s) return <p className="empty">Loading the room…</p>;

  const joinUrl = `${window.location.origin}/join/${s.room.code}`;
  const running = s.phase === "drawing" || s.phase === "collecting";
  const onDelete = () => {
    if (window.confirm(`Delete “${s.room.name}” with all its students and drawings? This cannot be undone.`)) remove.mutate(id, { onSuccess: () => navigate("/classroom") });
  };

  return (
    <div className="docs">
      <div className="page-head">
        <div><Link to="/classroom" className="meta">← All rooms</Link><h1>{s.room.name}</h1></div>
        <span className={`chip ${link === "live" ? "ok" : "loading"}`} role="status"><i className="dot" />{link === "live" ? "live" : "connecting…"}</span>
      </div>

      <section className="card join-card" aria-label="Join code">
        <div>
          <span className="meta">Students join with this code</span>
          <div className="join-code" aria-label={`Room code ${s.room.code.split("").join(" ")}`}>{s.room.code}</div>
          <span className="meta">at <code>{joinUrl}</code></span>
        </div>
        <div className="join-actions">
          {!s.room.closed && <button className="btn" disabled={close.isPending} onClick={() => close.mutate(id)}>Close room</button>}
          <button className="btn ghost" onClick={onDelete} disabled={remove.isPending}>Delete room</button>
        </div>
      </section>

      {s.phase === "closed" && <div className="toast" role="status">This room is closed. Students can no longer join or submit; the results below stay available.</div>}

      <div className="studio">
        <div className="stack">
          {running && <RunningRound roomId={id} s={s} />}
          {(s.phase === "lobby" || s.phase === "results") && !s.room.closed && <StartRound roomId={id} round={(s.round?.no ?? 0) + 1} />}
          {s.results && <ResultsBoard roomId={id} token={null} results={s.results} />}
        </div>
        <aside className="stack">
          <Roster members={s.members} phase={s.phase} />
          <TotalsCard totals={s.totals} rounds={s.rounds_finished} />
        </aside>
      </div>
    </div>
  );
}
