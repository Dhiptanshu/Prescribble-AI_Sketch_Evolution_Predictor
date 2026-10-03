import { StrokeThumb } from "../../components/StrokeThumb";
import { percent } from "../../lib/format";
import { useRoundDrawings, type RoundResults, type TotalEntry } from "../../lib/rooms";

function aiLine(ai: RoundResults["ai"], target: string): string {
  if (!ai.drawings) return "Nobody handed in a drawing this round.";
  if (!ai.named) return `The AI never recognised the ${target} in ${ai.drawings} drawing${ai.drawings === 1 ? "" : "s"}.`;
  const when = ai.median_recognised_at != null ? `, typically by ${percent(ai.median_recognised_at)} of the ink` : "";
  return `The AI named the ${target} in ${ai.named} of ${ai.drawings} drawing${ai.drawings === 1 ? "" : "s"}${when}.`;
}

/** A finished round: the AI's record, the ranking and everyone's drawings. Everything comes from the server's scored results. */
export function ResultsBoard({ roomId, token, results }: { roomId: number; token: string | null; results: RoundResults }) {
  const drawings = useRoundDrawings(roomId, results.round_no, token);
  const byId = new Map((drawings.data ?? []).map((d) => [d.submission_id, d]));
  return (
    <section className="card" aria-label={`Round ${results.round_no} results`}>
      <div className="card-head"><h2>Round {results.round_no} results</h2><span className="meta">word: <b>{results.target}</b></span></div>
      <p className="ai-line">{aiLine(results.ai, results.target)}</p>
      {results.entries.length > 0 && (
        <table aria-label={`Round ${results.round_no} ranking`}>
          <thead><tr><th>#</th><th>Student</th><th>Score</th><th>AI had it by</th><th>AI’s last guess</th></tr></thead>
          <tbody>
            {results.entries.map((e) => (
              <tr key={e.submission_id} className={e.is_me ? "me" : undefined}>
                <td>{e.rank ?? "–"}</td>
                <td>{e.nickname}{e.is_me ? " (you)" : ""}{!e.counted && <span className="pill"> not counted</span>}</td>
                <td>{e.score}</td>
                <td>{e.recognised_at != null ? percent(e.recognised_at) : "never"}</td>
                <td>{e.final_guess}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {results.entries.length > 0 && (
        <div className="gallery room-gallery" aria-label="The class’s drawings">
          {results.entries.map((e) => {
            const d = byId.get(e.submission_id);
            return d ? (
              <figure key={e.submission_id} className="room-drawing">
                <StrokeThumb strokes={d.strokes} label={`${e.nickname}’s drawing`} />
                <figcaption><b>{e.nickname}</b> <span className="meta">{e.score} pts</span></figcaption>
              </figure>
            ) : null;
          })}
        </div>
      )}
    </section>
  );
}

export function TotalsCard({ totals, rounds }: { totals: TotalEntry[]; rounds: number }) {
  return (
    <section className="card" aria-label="Class standings">
      <div className="card-head"><h2>Class standings</h2><span className="meta">{rounds} round{rounds === 1 ? "" : "s"} played</span></div>
      {totals.length ? (
        <table aria-label="Total points">
          <thead><tr><th>#</th><th>Student</th><th>Points</th><th>Rounds</th></tr></thead>
          <tbody>
            {totals.map((t) => (
              <tr key={t.nickname} className={t.is_me ? "me" : undefined}><td>{t.rank}</td><td>{t.nickname}{t.is_me ? " (you)" : ""}</td><td>{t.points}</td><td>{t.rounds_played}</td></tr>
            ))}
          </tbody>
        </table>
      ) : <p className="empty">Standings appear after the first round finishes.</p>}
    </section>
  );
}
