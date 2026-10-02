// Stroke pipeline: mirrors src/data/partial.py (the training pipeline) in a fixed 256x256 frame.
// Coordinates are in that frame no matter how large the canvas is on screen.
export type Point = [number, number];
export type Stroke = Point[];

export const FRAME = 255;
export const IMG = 64;
export const MAX_PTS = 128;
export const SEQ_FEATS = 5;

/** Tuned so canvas ink matches OpenCV thickness=2 used at training time (mean pixel error < 0.01). */
export const RASTER = { lineWidth: 3.5, offset: 0.5 };

/** Ramer-Douglas-Peucker on one stroke; makes live mouse input look like QuickDraw's simplified data. */
export function rdp(pts: Stroke, eps = 2.0): Stroke {
  if (pts.length < 3) return pts.slice();
  const [ax, ay] = pts[0]!;
  const [bx, by] = pts[pts.length - 1]!;
  const dx = bx - ax, dy = by - ay, norm = Math.hypot(dx, dy);
  let best = -1, idx = 0;
  for (let i = 1; i < pts.length - 1; i++) {
    const [px, py] = pts[i]!;
    const d = norm === 0 ? Math.hypot(px - ax, py - ay) : Math.abs(dx * (py - ay) - dy * (px - ax)) / norm;
    if (d > best) { best = d; idx = i; }
  }
  if (best > eps) {
    const left = rdp(pts.slice(0, idx + 1), eps), right = rdp(pts.slice(idx), eps);
    return left.slice(0, -1).concat(right);
  }
  return [pts[0]!, pts[pts.length - 1]!];
}

export function simplify(strokes: Stroke[]): Stroke[] {
  return strokes.map((s) => rdp(s)).filter((s) => s.length > 0);
}

/** Total ink length: the sum of segment lengths inside strokes. */
export function inkLength(strokes: Stroke[]): number {
  let total = 0;
  for (const s of strokes) for (let i = 1; i < s.length; i++) total += Math.hypot(s[i]![0] - s[i - 1]![0], s[i]![1] - s[i - 1]![1]);
  return total;
}

/** Keep the first `frac` of the ink (may stop mid-stroke). Mirrors cut_prefix() in Python. */
export function cutStrokes(strokes: Stroke[], frac: number): Stroke[] {
  if (frac >= 1) return strokes.map((s) => s.slice());
  let target = frac * inkLength(strokes);
  const out: Stroke[] = [];
  for (const s of strokes) {
    const part: Stroke = [s[0]!];
    for (let i = 1; i < s.length; i++) {
      const a = s[i - 1]!, b = s[i]!, d = Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (d >= target) {
        const t = d === 0 ? 0 : target / d;
        part.push([a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])]);
        out.push(part);
        return out;
      }
      target -= d;
      part.push(b);
    }
    out.push(part);
  }
  return out;
}

/** Stroke-sequence features, zero padded to MAX_PTS: x, y, dx*8, dy*8, new_stroke. */
export function toSeq(strokes: Stroke[]): { seq: Float32Array; length: number } {
  let pts: [number, number, number][] = [];
  for (const s of strokes) s.forEach((p, i) => pts.push([p[0], p[1], i === 0 ? 1 : 0]));
  if (pts.length > MAX_PTS) {
    const keep = new Set<number>();
    for (let i = 0; i < MAX_PTS; i++) keep.add(Math.round((i * (pts.length - 1)) / (MAX_PTS - 1)));
    pts = [...keep].sort((a, b) => a - b).map((i) => pts[i]!);
  }
  const seq = new Float32Array(MAX_PTS * SEQ_FEATS);
  pts.forEach((p, i) => {
    const o = i * SEQ_FEATS;
    seq[o] = p[0] / FRAME;
    seq[o + 1] = p[1] / FRAME;
    if (i > 0 && !p[2]) {
      seq[o + 2] = ((p[0] - pts[i - 1]![0]) / FRAME) * 8;
      seq[o + 3] = ((p[1] - pts[i - 1]![1]) / FRAME) * 8;
    }
    seq[o + 4] = i === 0 ? 1 : p[2];
  });
  return { seq, length: Math.max(pts.length, 1) };
}

let scratch: HTMLCanvasElement | OffscreenCanvas | null = null;
function scratchCanvas() {
  if (!scratch) scratch = typeof OffscreenCanvas !== "undefined" ? new OffscreenCanvas(IMG, IMG) : Object.assign(document.createElement("canvas"), { width: IMG, height: IMG });
  return scratch;
}

/** Rasterize into Float32Array(IMG*IMG) in [0,1] (white ink on black). Needs a 2D canvas (browser). */
export function rasterize(strokes: Stroke[]): Float32Array {
  const ctx = scratchCanvas().getContext("2d", { willReadFrequently: true }) as CanvasRenderingContext2D;
  ctx.fillStyle = "#000"; ctx.fillRect(0, 0, IMG, IMG);
  ctx.strokeStyle = "#fff"; ctx.fillStyle = "#fff";
  ctx.lineWidth = RASTER.lineWidth; ctx.lineCap = "round"; ctx.lineJoin = "round";
  const k = (IMG - 1) / FRAME, o = RASTER.offset;
  for (const s of strokes) {
    const first = s[0]!;
    if (s.length === 1) { ctx.beginPath(); ctx.arc(first[0] * k + o, first[1] * k + o, 1, 0, Math.PI * 2); ctx.fill(); continue; }
    ctx.beginPath(); ctx.moveTo(first[0] * k + o, first[1] * k + o);
    for (let i = 1; i < s.length; i++) ctx.lineTo(s[i]![0] * k + o, s[i]![1] * k + o);
    ctx.stroke();
  }
  const data = ctx.getImageData(0, 0, IMG, IMG).data;
  const out = new Float32Array(IMG * IMG);
  for (let i = 0; i < out.length; i++) out[i] = data[i * 4]! / 255;
  return out;
}
