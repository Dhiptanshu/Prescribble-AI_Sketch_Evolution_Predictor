import { useState, type ReactNode } from "react";
import { ConfidenceChart } from "../../components/ConfidenceChart";
import { DrawingBoard } from "../../components/DrawingBoard";
import { GuessPanel } from "../../components/GuessPanel";
import { useEngine } from "../../lib/engine";
import { ChallengeMode } from "./modes/ChallengeMode";
import { ReplayMode } from "./modes/ReplayMode";
import type { ModeContext } from "./modes/types";
import { SavePanel } from "./SavePanel";
import { useDrawSession } from "./useDrawSession";
import { usePredictionLoop } from "./usePredictionLoop";

type Mode = "free" | "challenge" | "replay";
const MODES: { id: Mode; label: string }[] = [
  { id: "free", label: "Free draw" },
  { id: "challenge", label: "AI challenge" },
  { id: "replay", label: "Watch real sketches" },
];

export function StudioPage() {
  const engine = useEngine();
  const model = engine.status === "ready" ? engine.model : null;
  const loop = usePredictionLoop(model);
  const { boardRef, meta, revision, onChange, getStrokes, getDurationMs, getInputType } = useDrawSession(loop);

  const [mode, setMode] = useState<Mode>("free");
  const [locked, setLocked] = useState(false);
  const [truth, setTruth] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | undefined>();
  const [banner, setBanner] = useState<ReactNode>(null);

  const switchMode = (m: Mode) => {
    if (m === mode) return;
    boardRef.current?.clear();
    setLocked(false); setTruth(null); setProgress(undefined); setBanner(null);
    setMode(m);
  };

  const ctx: ModeContext = {
    classes: model?.classes ?? [], last: loop.last, boardRef, predictNow: loop.run,
    setLocked, setBanner, setTruth, setProgress,
  };
  const freeBanner = "Draw anything from the list. The AI updates its guesses after every stroke.";

  return (
    <div className="studio">
      <section className="card" aria-label="Drawing studio">
        <nav className="tabs" aria-label="Studio mode">
          {MODES.map((m) => (
            <button key={m.id} className={"tab" + (mode === m.id ? " active" : "")} onClick={() => switchMode(m.id)}>{m.label}</button>
          ))}
        </nav>
        <div className="banner">{mode === "free" ? freeBanner : banner}</div>
        <DrawingBoard
          ref={boardRef}
          onChange={onChange}
          locked={locked || !model}
          hint={model ? "Draw big, anywhere in the box. The AI starts guessing after your first stroke." : "Loading the model…"}
          progress={progress}
        />
        <div className="toolbar">
          <button className="btn" onClick={() => boardRef.current?.undo()} disabled={!meta.strokes || mode === "replay"}>Undo stroke</button>
          <button className="btn" onClick={() => boardRef.current?.clear()} disabled={mode === "replay"}>Clear</button>
          <span className="spacer" />
          <span className="meta">{meta.strokes} stroke{meta.strokes === 1 ? "" : "s"} · {meta.ink} px ink</span>
        </div>
      </section>

      <aside className="stack">
        <section className="card" aria-label="Top-5 guesses">
          <div className="card-head">
            <h2>Top-5 guesses</h2>
            <span className="meta">{loop.last ? `certainty ${Math.round((1 - loop.last.entropy) * 100)}% · ${Math.round(loop.last.ms)} ms` : "—"}</span>
          </div>
          <GuessPanel prediction={loop.last} truth={truth} />
        </section>
        <section className="card" aria-label="Confidence over time">
          <div className="card-head"><h2>Confidence over time</h2><span className="meta">x = ink drawn</span></div>
          <ConfidenceChart history={loop.history} classes={model?.classes ?? []} />
        </section>
        {mode !== "replay" && model && (
          <SavePanel
            mode={mode} classes={model.classes} last={loop.last} history={loop.history} revision={revision}
            getStrokes={getStrokes} getDurationMs={getDurationMs} getInputType={getInputType}
          />
        )}
        {mode === "challenge" && model && <ChallengeMode {...ctx} />}
        {mode === "replay" && model && <ReplayMode {...ctx} />}
      </aside>
    </div>
  );
}
