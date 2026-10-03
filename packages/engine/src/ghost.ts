import type { Prediction } from "./model";
import { IMG } from "./pipeline";

/**
 * RGBA pixels (IMG x IMG) of the model's own prediction of how the drawing will end, in the accent colour.
 * Only the *not yet drawn* part is visible: pixels within 2 px of existing ink are masked out.
 */
export function ghostPixels(p: Prediction): Uint8ClampedArray {
  const out = new Uint8ClampedArray(IMG * IMG * 4), { ghost, img } = p;
  const near = (x: number, y: number) => {
    for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) {
      const xx = x + dx, yy = y + dy;
      if (xx >= 0 && yy >= 0 && xx < IMG && yy < IMG && img[yy * IMG + xx]! > 0.2) return true;
    }
    return false;
  };
  for (let y = 0; y < IMG; y++) for (let x = 0; x < IMG; x++) {
    const i = y * IMG + x;
    const v = near(x, y) ? 0 : Math.max(0, Math.min(1, (ghost[i]! - 0.15) / 0.6));      // ignore faint background haze
    out[i * 4] = 124; out[i * 4 + 1] = 92; out[i * 4 + 2] = 255; out[i * 4 + 3] = v * 170;
  }
  return out;
}
