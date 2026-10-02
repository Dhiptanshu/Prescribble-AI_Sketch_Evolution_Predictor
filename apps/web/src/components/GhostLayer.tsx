import { useEffect, useRef } from "react";
import { IMG, type Prediction } from "@prescribble/engine";

/**
 * The model's own prediction of how the drawing will end, drawn in the accent colour.
 * Only the *not yet drawn* part is shown: pixels near existing ink are masked out.
 */
export function GhostLayer({ prediction, enabled }: { prediction: Prediction | null; enabled: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const ctx = ref.current!.getContext("2d")!;
    ctx.clearRect(0, 0, IMG, IMG);
    if (!prediction || !enabled) return;
    const id = ctx.createImageData(IMG, IMG), { ghost, img } = prediction;
    const near = (x: number, y: number) => {
      for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) {
        const xx = x + dx, yy = y + dy;
        if (xx >= 0 && yy >= 0 && xx < IMG && yy < IMG && img[yy * IMG + xx]! > 0.2) return true;
      }
      return false;
    };
    for (let y = 0; y < IMG; y++) for (let x = 0; x < IMG; x++) {
      const i = y * IMG + x;
      const v = near(x, y) ? 0 : Math.max(0, Math.min(1, (ghost[i]! - 0.15) / 0.6));   // ignore faint background haze
      id.data[i * 4] = 124; id.data[i * 4 + 1] = 92; id.data[i * 4 + 2] = 255; id.data[i * 4 + 3] = v * 170;
    }
    ctx.putImageData(id, 0, 0);
  }, [prediction, enabled]);

  return <canvas ref={ref} width={IMG} height={IMG} aria-hidden="true" style={{ opacity: enabled ? 1 : 0, transition: "opacity .25s" }} />;
}
