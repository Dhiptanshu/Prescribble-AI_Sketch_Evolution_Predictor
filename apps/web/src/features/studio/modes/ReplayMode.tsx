import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cutStrokes, inkLength } from "@prescribble/engine/pipeline";
import type { Stroke } from "@prescribble/engine";
import { useEngine } from "../../../lib/engine";
import type { ModeContext } from "./types";

interface Sample { label: string; strokes: Stroke[] }
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Replays real held-out QuickDraw sketches (never trained on) stroke by stroke through the live model. */
export function ReplayMode({ boardRef, predictNow, setLocked, setBanner, setTruth, setProgress }: ModeContext) {
  const [samples, setSamples] = useState<Sample[] | null>(null);
  const [label, setLabel] = useState("");
  const [sample, setSample] = useState<Sample | null>(null);
  const [playing, setPlaying] = useState(false);
  const [summary, setSummary] = useState<{ ok: boolean; text: string } | null>(null);
  const run = useRef(0);
  const engine = useEngine();
  const version = engine.status === "ready" ? engine.version : null;

  useEffect(() => {
    if (!version) return;
    let alive = true;
    fetch(`${import.meta.env.BASE_URL}models/${version}/samples.json`)
      .then((r) => r.json() as Promise<Sample[]>)
      .then((s) => alive && setSamples(s))
      .catch(() => alive && setSamples([]));
    // `run` is a cancellation counter, not a DOM ref: bumping it on unmount stops any playback still in flight.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    return () => { alive = false; run.current++; };
  }, [version]);

  const labels = useMemo(() => [...new Set((samples ?? []).map((s) => s.label))], [samples]);

  const pick = useCallback((l: string) => {
    if (!samples?.length) return;
    run.current++; setPlaying(false); setSummary(null);
    const pool = samples.filter((s) => s.label === l);
    const s = pool[Math.floor(Math.random() * pool.length)]!;
    setSample(s); setTruth(s.label); setProgress(0); setLocked(true);
    boardRef.current?.clear();
    setBanner(<>Ground truth: <b>{s.label}</b>. Press play to watch the model guess as the sketch is drawn.</>);
  }, [samples, boardRef, setTruth, setProgress, setLocked, setBanner]);

  useEffect(() => { if (labels.length && !label) { setLabel(labels[0]!); pick(labels[0]!); } }, [labels, label, pick]);

  async function play() {
    if (!sample) return;
    if (playing) { run.current++; setPlaying(false); return; }
    const id = ++run.current;
    setPlaying(true); setSummary(null);
    const steps = 50, trace: { frac: number; top1: boolean; top5: boolean }[] = [];
    for (let i = 1; i <= steps && run.current === id; i++) {
      const frac = i / steps, cut = cutStrokes(sample.strokes, frac);
      boardRef.current?.set(cut);
      setProgress(frac);
      const pred = await predictNow(cut, i === 1 || i % 5 === 0);
      const top = pred?.top5 ?? [];
      trace.push({ frac, top1: top[0]?.name === sample.label, top5: top.some((g) => g.name === sample.label) });
      await sleep(70);
    }
    if (run.current === id) {
      const stable = (k: "top1" | "top5") => { let i = trace.length; while (i > 0 && trace[i - 1]![k]) i--; return i < trace.length ? trace[i]!.frac : null; };
      const f = (v: number | null) => (v == null ? "never" : `${Math.round(v * 100)}% of the ink`);
      const t5 = stable("top5"), t1 = stable("top1");
      setSummary({ ok: t5 != null, text: `Correct in the Top-5 (and staying correct) from ${f(t5)}; as the #1 guess from ${f(t1)}.` });
    }
    setPlaying(false);
  }

  if (samples && !samples.length) return <div className="card"><p className="empty">No sample sketches found for this model version.</p></div>;
  const total = sample ? Math.round(inkLength(sample.strokes)) : 0;
  return (
    <div className="card">
      <div className="card-head"><h2>Real QuickDraw test sketches</h2><span className="meta">never seen in training</span></div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <select className="input" style={{ width: "auto" }} value={label} onChange={(e) => { setLabel(e.target.value); pick(e.target.value); }} aria-label="Object class">
          {labels.map((l) => <option key={l}>{l}</option>)}
        </select>
        <button className="btn" onClick={() => pick(label)}>Another sketch</button>
        <button className="btn primary" onClick={play} disabled={!sample}>{playing ? "■ Stop" : "▶ Play"}</button>
        <span className="meta">{total ? `${total} px of ink` : ""}</span>
      </div>
      {summary && <div className={"toast " + (summary.ok ? "good" : "bad")} role="status" style={{ marginTop: 12 }}>{summary.text}</div>}
    </div>
  );
}
