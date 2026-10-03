import { useCallback, useRef, useState, type ReactNode } from "react";
import { inkLength } from "@prescribble/engine/pipeline";
import type { Stroke } from "@prescribble/engine";
import { ConfidenceChart } from "../../components/ConfidenceChart";
import { DrawingBoard, type BoardHandle, type BoardPhase } from "../../components/DrawingBoard";
import { GhostLayer } from "../../components/GhostLayer";
import { GuessPanel } from "../../components/GuessPanel";
import { useEngine } from "../../lib/engine";
import { ChallengeMode } from "./modes/ChallengeMode";
import { ReplayMode } from "./modes/ReplayMode";
import type { ModeContext } from "./modes/types";
import { SavePanel } from "./SavePanel";
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
  const boardRef = useRef<BoardHandle>(null);

  const [mode, setMode] = useState<Mode>("free");
  const [ghost, setGhost] = useState(true);
  const [locked, setLocked] = useState(false);
  const [truth, setTruth] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | undefined>();
  const [banner, setBanner] = useState<ReactNode>(null);
  const [meta, setMeta] = useState({ strokes: 0, ink: 0 });
  const [revision, setRevision] = useState(0);                    // bumps whenever the user changes the drawing
  const timing = useRef<{ start: number | null; end: number | null }>({ start: null, end: null });

  const onBoardChange = useCallback((strokes: Stroke[], phase: BoardPhase) => {
    setMeta({ strokes: strokes.length, ink: Math.round(inkLength(strokes)) });
    if (phase === "set") return;                                  // scripted playback runs the model itself
    if (phase === "start" && strokes.length === 1) timing.current = { start: performance.now(), end: null };
    if (phase === "end") timing.current.end = performance.now();
    if (phase === "clear") timing.current = { start: null, end: null };
    setRevision((r) => r + 1);
    if (!strokes.length) { loop.reset(); return; }
    void loop.run(strokes, phase === "end" || phase === "undo" || phase === "start");
  }, [loop]);

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
  const freeBanner = "Draw anything from the list. The purple ghost is the model’s own prediction of how your drawing will end.";

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
          onChange={onBoardChange}
          locked={locked || !model}
          underlay={<GhostLayer prediction={loop.last} enabled={ghost} />}
          hint={model ? "Draw big, anywhere in the box. The AI starts guessing after your first stroke." : "Loading the model…"}
          progress={progress}
        />
        <div className="toolbar">
          <button className="btn" onClick={() => boardRef.current?.undo()} disabled={!meta.strokes || mode === "replay"}>Undo stroke</button>
          <button className="btn" onClick={() => boardRef.current?.clear()} disabled={mode === "replay"}>Clear</button>
          <label className="switch">
            <input type="checkbox" checked={ghost} onChange={(e) => setGhost(e.target.checked)} />
            <i /> Ghost completion
          </label>
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
            getStrokes={() => boardRef.current?.strokes() ?? []}
            getDurationMs={() => (timing.current.start != null && timing.current.end != null ? Math.round(timing.current.end - timing.current.start) : null)}
          />
        )}
        {mode === "challenge" && model && <ChallengeMode {...ctx} />}
        {mode === "replay" && model && <ReplayMode {...ctx} />}
      </aside>
    </div>
  );
}
