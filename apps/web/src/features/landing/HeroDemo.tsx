import { useEffect, useRef, useState } from "react";
import { cutStrokes, type Stroke } from "@prescribble/engine";
import { DrawingBoard, type BoardHandle } from "../../components/DrawingBoard";
import { GhostLayer } from "../../components/GhostLayer";
import { GuessPanel } from "../../components/GuessPanel";
import { MODEL_VERSION, useEngine } from "../../lib/engine";
import { usePredictionLoop } from "../studio/usePredictionLoop";

interface Sample { label: string; strokes: Stroke[] }
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** A real held-out QuickDraw sketch, replayed through the real model on a loop. Nothing here is scripted or faked. */
export function HeroDemo() {
  const engine = useEngine();
  const model = engine.status === "ready" ? engine.model : null;
  const { last, run, reset } = usePredictionLoop(model);
  const board = useRef<BoardHandle>(null);
  const [truth, setTruth] = useState<string | null>(null);
  const [frac, setFrac] = useState(0);

  useEffect(() => {
    if (!model) return;
    let alive = true;
    (async () => {
      let samples: Sample[] = [];
      try { samples = await (await fetch(`${import.meta.env.BASE_URL}models/${MODEL_VERSION}/samples.json`)).json(); } catch { return; }
      while (alive && samples.length) {
        const s = samples[Math.floor(Math.random() * samples.length)]!;
        setTruth(s.label); setFrac(0); board.current?.clear(); reset();
        await sleep(600);
        const steps = 40;
        for (let i = 1; i <= steps && alive; i++) {
          const cut = cutStrokes(s.strokes, i / steps);
          board.current?.set(cut); setFrac(i / steps);
          await run(cut, i % 5 === 0);
          await sleep(70);
        }
        await sleep(2000);
      }
    })();
    return () => { alive = false; };
  }, [model, run, reset]);

  return (
    <div className="card" aria-label="Live demo">
      <div className="card-head">
        <h2>Live: a real sketch, drawn live</h2>
        <span className="meta">{truth ? `ground truth: ${truth}` : "loading…"}</span>
      </div>
      <DrawingBoard ref={board} onChange={() => {}} locked underlay={<GhostLayer prediction={last} enabled />} progress={frac} />
      <div style={{ marginTop: 14 }}><GuessPanel prediction={last} truth={truth} /></div>
    </div>
  );
}
