import { FRAME } from "@prescribble/engine/pipeline";
import type { Stroke } from "@prescribble/engine/pipeline";

export const cssVar = (name: string, fallback: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

/** Draw strokes (0..255 frame) onto a square canvas context of `size` pixels. */
export function paintStrokes(ctx: CanvasRenderingContext2D, strokes: Stroke[], size: number, lineWidth: number, color = cssVar("--ink", "#fff")) {
  const k = size / FRAME;
  ctx.strokeStyle = color; ctx.fillStyle = color;
  ctx.lineWidth = lineWidth; ctx.lineCap = "round"; ctx.lineJoin = "round";
  for (const s of strokes) {
    const first = s[0];
    if (!first) continue;
    if (s.length === 1) { ctx.beginPath(); ctx.arc(first[0] * k, first[1] * k, lineWidth / 2, 0, 7); ctx.fill(); continue; }
    ctx.beginPath(); ctx.moveTo(first[0] * k, first[1] * k);
    for (let i = 1; i < s.length; i++) ctx.lineTo(s[i]![0] * k, s[i]![1] * k);
    ctx.stroke();
  }
}
