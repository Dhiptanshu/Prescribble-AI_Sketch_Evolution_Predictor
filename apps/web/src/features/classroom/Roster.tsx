import type { Member, Phase } from "../../lib/rooms";

/** Who is in the room. During a round it also shows who has handed in a drawing (never their score). */
export function Roster({ members, phase }: { members: Member[]; phase: Phase }) {
  const running = phase === "drawing" || phase === "collecting";
  const done = members.filter((m) => m.submitted).length;
  return (
    <section className="card" aria-label="Students">
      <div className="card-head">
        <h2>Students</h2>
        <span className="meta" aria-live="polite">{running ? `${done} of ${members.length} handed in` : `${members.length} joined`}</span>
      </div>
      {members.length ? (
        <ul className="roster">
          {members.map((m) => (
            <li key={m.nickname} className={m.online ? "on" : "off"}>
              <i className="dot" aria-hidden="true" />
              <span>{m.nickname}{m.is_me ? " (you)" : ""}</span>
              <span className="meta">{running && m.submitted ? "handed in" : m.online ? "" : "offline"}</span>
            </li>
          ))}
        </ul>
      ) : <p className="empty">Nobody has joined yet. Share the code.</p>}
    </section>
  );
}
