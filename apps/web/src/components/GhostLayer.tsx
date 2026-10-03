import { useEffect, useRef } from "react";
import { IMG } from "@prescribble/engine/pipeline";
import type { Prediction } from "@prescribble/engine";
import { ghostPixels } from "../lib/ghost";

/** The model's own prediction of how the drawing will end, drawn in the accent colour (see lib/ghost.ts). */
export function GhostLayer({ prediction, enabled }: { prediction: Prediction | null; enabled: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const ctx = ref.current!.getContext("2d")!;
    ctx.clearRect(0, 0, IMG, IMG);
    if (!prediction || !enabled) return;
    const image = ctx.createImageData(IMG, IMG);
    image.data.set(ghostPixels(prediction));
    ctx.putImageData(image, 0, 0);
  }, [prediction, enabled]);

  return <canvas ref={ref} width={IMG} height={IMG} aria-hidden="true" style={{ opacity: enabled ? 1 : 0, transition: "opacity .25s" }} />;
}
