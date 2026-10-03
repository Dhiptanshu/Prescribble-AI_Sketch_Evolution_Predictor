import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../lib/api";
import { joinRoom, saveRoomToken } from "../../lib/rooms";

/** Students enter the teacher's code and a nickname. No account, no email. */
export function JoinPage() {
  const navigate = useNavigate();
  const [code, setCode] = useState(useParams().code ?? "");
  const [nickname, setNickname] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const j = await joinRoom(code, nickname);
      saveRoomToken(j.room_id, j.token, j.nickname);
      navigate(`/room/${j.room_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server.");
    } finally { setBusy(false); }
  }

  return (
    <div className="auth-wrap card">
      <h1>Join a room</h1>
      <p className="sub">Type the code your teacher shows you and pick a nickname. Your classmates will see the nickname, nothing else.</p>
      <form onSubmit={onSubmit} className="stack" style={{ gap: 14 }}>
        <div className="field">
          <label htmlFor="code">Room code</label>
          <input id="code" className="input code-input" autoComplete="off" autoCapitalize="characters" spellCheck={false} maxLength={12}
                 value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} />
        </div>
        <div className="field">
          <label htmlFor="nick">Nickname</label>
          <input id="nick" className="input" autoComplete="off" maxLength={24} value={nickname} onChange={(e) => setNickname(e.target.value)} />
        </div>
        {error && <div className="toast bad" role="alert">{error}</div>}
        <button className="btn primary lg" disabled={busy || !code.trim() || !nickname.trim()}>{busy ? "Joining…" : "Join"}</button>
      </form>
    </div>
  );
}
