import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../../lib/api";
import { formatDate } from "../../lib/format";
import { useMyRooms, useRoomActions } from "../../lib/rooms";

/** The teacher's home: create a room, reopen one, or find the join page for students. */
export function ClassroomsPage() {
  const rooms = useMyRooms();
  const { create } = useRoomActions();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const error = create.error instanceof ApiError ? create.error.message : create.error ? "Could not reach the server." : null;

  function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    create.mutate(name.trim(), { onSuccess: (r) => navigate(`/classroom/${r.id}`) });
  }

  return (
    <div className="docs">
      <div className="page-head"><h1>Classrooms</h1><Link className="btn" to="/join">Join a room as a student</Link></div>
      <p className="lead-docs">Start a room, share the code, and your students draw the same word while the AI races them. Students need no account.</p>

      <section className="card" aria-label="Create a room">
        <div className="card-head"><h2>New room</h2></div>
        <form className="field key-form" onSubmit={onCreate}>
          <div className="field">
            <label htmlFor="room-name">Room name</label>
            <input id="room-name" className="input" value={name} maxLength={60} placeholder="e.g. Period 3 art" onChange={(e) => setName(e.target.value)} />
          </div>
          <button className="btn primary" disabled={!name.trim() || create.isPending}>{create.isPending ? "Creating…" : "Create room"}</button>
        </form>
        {error && <div className="toast bad" role="alert" style={{ marginTop: 10 }}>{error}</div>}
      </section>

      <section className="card" aria-label="Your rooms">
        <div className="card-head"><h2>Your rooms</h2></div>
        {rooms.isLoading ? <p className="empty">Loading…</p> : rooms.isError ? <p className="empty">Could not load your rooms.</p> : !rooms.data?.length ? (
          <p className="empty">You have no rooms yet. Create one above.</p>
        ) : (
          <table aria-label="Rooms">
            <thead><tr><th>Room</th><th>Code</th><th>Students</th><th>Rounds</th><th>Created</th><th /></tr></thead>
            <tbody>
              {rooms.data.map((r) => (
                <tr key={r.id} className={r.closed ? "revoked" : undefined}>
                  <td><Link to={`/classroom/${r.id}`}>{r.name}</Link>{r.closed && <span className="pill"> closed</span>}</td>
                  <td><code>{r.code}</code></td><td>{r.members}</td><td>{r.rounds}</td><td>{formatDate(r.created_at)}</td>
                  <td className="actions"><Link className="btn" to={`/classroom/${r.id}`}>Open</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
