import { useCallback, useEffect, useRef, useState } from "react";
import { AiWinsDialog } from "./AiWinsDialog";
import type { ModeContext } from "./types";

interface Stats { rounds: number; wins: number; strokes: number[] }

/**
 * Local AI challenge: the AI wins when it names the target with >= 50% confidence before you stop drawing.
 * To keep the race fair the win is decided on the exact strokes the model scored: the pen stops and the drawing is cut back to what the AI saw.
 */
export function ChallengeMode({ classes, last, lastInput, boardRef, setLocked, setBanner, setTruth }: ModeContext) {
  const [target, setTarget] = useState("");
  const [result, setResult] = useState<{ won: boolean; text: string } | null>(null);
  const [win, setWin] = useState<{ strokes: number; confidence: number } | null>(null);
  const [stats, setStats] = useState<Stats>({ rounds: 0, wins: 0, strokes: [] });
  const active = useRef(false);

  const newRound = useCallback(() => {
    const t = classes[Math.floor(Math.random() * classes.length)]!;
    setTarget(t); setResult(null); setWin(null); setTruth(null); setLocked(false);
    active.current = true;
    boardRef.current?.clear();
    setBanner(<>Draw: <b>{t}</b>. The AI wins if it recognises it (≥ 50% confidence) before you finish.</>);
  }, [classes, boardRef, setLocked, setBanner, setTruth]);

  useEffect(() => { newRound(); return () => { active.current = false; }; }, [newRound]);

  const finish = useCallback((won: boolean, guess?: { name: string; p: number }) => {
    if (!active.current) return;
    active.current = false;
    setLocked(true);
    // The AI's win is judged on what it saw: cut the drawing back to that snapshot (this also ends a stroke still in progress).
    const strokes = won && lastInput ? lastInput : boardRef.current?.strokes() ?? [];
    if (won && lastInput) boardRef.current?.set(lastInput);
    const n = strokes.length;
    if (won) setWin({ strokes: n, confidence: guess?.p ?? 1 });
    setStats((s) => ({ rounds: s.rounds + 1, wins: s.wins + (won ? 1 : 0), strokes: won ? [...s.strokes, n] : s.strokes }));
    setResult(won
      ? { won, text: `The AI recognised ${target} after ${n} stroke${n === 1 ? "" : "s"}.` }
      : { won, text: guess ? `The AI did not get it. Its best guess was ${guess.name} (${Math.round(guess.p * 100)}%).` : "Nothing was drawn." });
  }, [boardRef, setLocked, target, lastInput]);

  useEffect(() => {
    const t = last?.top5[0];
    if (active.current && t && t.name === target && t.p >= 0.5) finish(true, t);
  }, [last, target, finish]);

  const avg = stats.strokes.length ? (stats.strokes.reduce((a, b) => a + b, 0) / stats.strokes.length).toFixed(1) : "–";
  return (
    <div className="card">
      <div className="card-head"><h2>AI challenge</h2><span className="meta">you vs the model</span></div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, marginBottom: 10 }}>
        <div style={{ fontSize: 28, fontWeight: 780, letterSpacing: "-.02em" }}>{target || "–"}</div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn primary" onClick={newRound}>New word</button>
          <button className="btn" onClick={() => finish(false, last?.top5[0])}>Give up</button>
        </div>
      </div>
      {win && <AiWinsDialog target={target} strokes={win.strokes} confidence={win.confidence} onNext={newRound} onClose={() => setWin(null)} />}
      {result && <div className={"toast " + (result.won ? "good" : "bad")} role="status">{result.text}</div>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10, marginTop: 12 }}>
        {[[stats.rounds, "rounds"], [stats.wins, "AI got it"], [avg, "avg strokes needed"]].map(([v, l]) => (
          <div key={String(l)} style={{ background: "rgba(127,127,160,.1)", borderRadius: 12, padding: 10, textAlign: "center" }}>
            <b style={{ display: "block", fontSize: 22 }}>{v}</b><span className="meta">{l}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
