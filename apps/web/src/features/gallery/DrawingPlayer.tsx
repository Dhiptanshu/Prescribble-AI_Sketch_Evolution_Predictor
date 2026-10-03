import { useCallback, useEffect, useRef, useState } from "react";
import { IMG, cutStrokes } from "@prescribble/engine/pipeline";
import type { Stroke } from "@prescribble/engine/pipeline";
import type { Prediction, SketchModel } from "@prescribble/engine";
import { ghostPixels } from "@prescribble/engine/ghost";
import { cssVar, paintStrokes } from "../../lib/paint";
import { canRecord, recordCanvas } from "./recordVideo";

const SIZE = 640;        // backing resolution of the canvas (and of exported videos); CSS scales it
const STEPS = 60;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

interface Frame { cut: Stroke[]; pred: Prediction | null; frac: number }

/**
 * Replays a saved drawing stroke by stroke through the real model (nothing is recorded or faked), with the ghost and a live caption.
 * The same canvas can be exported as a .webm video.
 */
export function DrawingPlayer({ strokes, model, title, exportName }: { strokes: Stroke[]; model: SketchModel; title: string; exportName: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const ghostCanvas = useRef<HTMLCanvasElement | null>(null);
  const frame = useRef<Frame>({ cut: strokes, pred: null, frac: 1 });
  const token = useRef(0);                                  // bumped to cancel playback or stale seeks
  const [frac, setFrac] = useState(1);
  const [playing, setPlaying] = useState(false);
  const [exporting, setExporting] = useState(false);

  const render = useCallback(() => {
    const c = canvas.current;
    if (!c) return;
    const ctx = c.getContext("2d")!, { cut, pred, frac: f } = frame.current;
    ctx.fillStyle = cssVar("--paper", "#0f1220");
    ctx.fillRect(0, 0, SIZE, SIZE);
    if (pred) {
      const g = (ghostCanvas.current ??= Object.assign(document.createElement("canvas"), { width: IMG, height: IMG }));
      const gctx = g.getContext("2d")!, image = gctx.createImageData(IMG, IMG);
      image.data.set(ghostPixels(pred));
      gctx.putImageData(image, 0, 0);
      ctx.imageSmoothingEnabled = true;
      ctx.drawImage(g, 0, 0, SIZE, SIZE);
    }
    paintStrokes(ctx, cut, SIZE, 9);
    // caption: the AI's current best guess, as it was at this moment of the drawing
    ctx.fillStyle = "rgba(10, 12, 24, .72)";
    ctx.fillRect(0, SIZE - 92, SIZE, 92);
    const top = pred?.top5[0];
    ctx.fillStyle = "#f5f6fb"; ctx.textBaseline = "alphabetic";
    ctx.font = "700 38px system-ui, sans-serif";
    ctx.fillText(top ? top.name : "…", 24, SIZE - 40);
    if (top) {
      ctx.fillStyle = "#9aa0bd"; ctx.font = "500 24px system-ui, sans-serif";
      ctx.fillText(`${Math.round(top.p * 100)}% sure · ${Math.round(f * 100)}% of the ink`, 24, SIZE - 12);
    }
    const grad = ctx.createLinearGradient(0, 0, SIZE, 0);
    grad.addColorStop(0, "#7c5cff"); grad.addColorStop(1, "#22d3ee");
    ctx.fillStyle = grad;
    ctx.fillRect(0, SIZE - 6, SIZE * f, 6);
  }, []);

  /** Show the drawing as it was at `f` of its ink; resolves false if something newer took over. */
  const showAt = useCallback(async (f: number, id: number) => {
    const cut = cutStrokes(strokes, f), pred = await model.predict(cut);
    if (token.current !== id) return false;
    frame.current = { cut, pred, frac: f };
    render(); setFrac(f);
    return true;
  }, [strokes, model, render]);

  const stop = useCallback(() => { token.current++; setPlaying(false); }, []);

  const play = useCallback(async () => {
    const id = ++token.current;
    setPlaying(true);
    for (let i = 1; i <= STEPS; i++) {
      const t0 = performance.now();
      if (!(await showAt(i / STEPS, id))) return;
      await sleep(Math.max(0, 55 - (performance.now() - t0)));
    }
    if (token.current === id) setPlaying(false);
  }, [showAt]);

  // Show the finished drawing (with the AI's final guess) as soon as the player mounts or the drawing changes.
  useEffect(() => {
    void showAt(1, ++token.current);
    const mo = new MutationObserver(render);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    // `token` is a cancellation counter, not a DOM ref: bumping it on unmount stops any playback still in flight.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    return () => { token.current++; mo.disconnect(); };
  }, [showAt, render]);

  async function exportVideo() {
    setExporting(true);
    try {
      await recordCanvas(canvas.current!, play, `${exportName}.webm`);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="player">
      <canvas ref={canvas} width={SIZE} height={SIZE} className="player-canvas" role="img" aria-label={title} />
      <div className="player-controls">
        <button className="btn primary" onClick={playing ? stop : () => void play()} disabled={exporting}>
          {playing ? "■ Stop" : frac >= 1 ? "▶ Replay" : "▶ Play"}
        </button>
        <input
          type="range" min={2} max={100} value={Math.round(frac * 100)} disabled={exporting} aria-label="Position in the drawing"
          onChange={(e) => { stop(); void showAt(Number(e.target.value) / 100, ++token.current); }}
        />
        <span className="meta" aria-live="off">{Math.round(frac * 100)}% of the ink</span>
        {canRecord() && <button className="btn" onClick={() => void exportVideo()} disabled={exporting || playing}>{exporting ? "Recording…" : "Save as video"}</button>}
      </div>
    </div>
  );
}
