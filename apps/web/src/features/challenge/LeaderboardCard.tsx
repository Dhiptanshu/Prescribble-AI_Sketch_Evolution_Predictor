import { useState } from "react";
import { previousDay, useLeaderboard, type LeaderboardEntry } from "../../lib/challenge";
import { percent } from "../../lib/format";

function Row({ e }: { e: LeaderboardEntry }) {
  return (
    <tr className={e.is_me ? "me" : undefined} aria-current={e.is_me ? "true" : undefined}>
      <td>{e.rank}</td>
      <td>{e.name}{e.is_me ? " (you)" : ""}</td>
      <td>{e.score}</td>
      <td>{e.recognised_at != null ? percent(e.recognised_at) : "–"}</td>
    </tr>
  );
}

/** Today's and yesterday's boards. Everything is read from the server; an empty board says so instead of showing filler. */
export function LeaderboardCard({ today }: { today: string }) {
  const [tab, setTab] = useState<"today" | "yesterday">("today");
  const q = useLeaderboard(tab === "yesterday" ? previousDay(today) : undefined);
  const b = q.data;
  const meOutside = b?.me && !b.entries.some((e) => e.is_me);

  return (
    <section className="card" aria-label="Leaderboard">
      <div className="card-head">
        <h2>Leaderboard</h2>
        <div className="seg" role="tablist" aria-label="Which day">
          {(["today", "yesterday"] as const).map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>{t === "today" ? "Today" : "Yesterday"}</button>
          ))}
        </div>
      </div>
      {q.isLoading && <p className="empty">Loading…</p>}
      {q.isError && <p className="empty">{tab === "yesterday" ? "There was no challenge yesterday." : "Could not load the leaderboard."}</p>}
      {b && (
        <>
          <p className="meta" style={{ marginBottom: 8 }}>
            Word: <b>{b.target}</b> · {b.participants} player{b.participants === 1 ? "" : "s"}
          </p>
          {b.entries.length ? (
            <table aria-label={`Leaderboard for ${b.day}`}>
              <thead><tr><th>#</th><th>Player</th><th>Score</th><th>AI had it by</th></tr></thead>
              <tbody>
                {b.entries.map((e) => <Row key={e.rank} e={e} />)}
                {meOutside && b.me && (<><tr><td colSpan={4} className="gap">…</td></tr><Row e={b.me} /></>)}
              </tbody>
            </table>
          ) : (
            <p className="empty">{tab === "today" ? "Nobody has scored yet today. Be the first." : "Nobody scored that day."}</p>
          )}
        </>
      )}
    </section>
  );
}
