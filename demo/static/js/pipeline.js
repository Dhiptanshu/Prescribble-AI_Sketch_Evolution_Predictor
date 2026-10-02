// Pure data pipeline. Mirrors src/data/partial.py exactly: fixed 256x256 frame, RDP simplify,
// raster (64x64) and stroke-sequence features (128 x 5).
export const FRAME = 255;
export const IMG = 64;
export const MAX_PTS = 128;
export const SEQ_FEATS = 5;
export const cfg = { lineWidth: 3.5 };   // tuned so canvas ink matches OpenCV thickness=2 (see tests/parity)

// Ramer-Douglas-Peucker on one stroke: [[x,y],...]
export function rdp(pts, eps = 2.0) {
  if (pts.length < 3) return pts.slice();
  const [ax, ay] = pts[0], [bx, by] = pts[pts.length - 1];
  const dx = bx - ax, dy = by - ay, norm = Math.hypot(dx, dy);
  let best = -1, idx = 0;
  for (let i = 1; i < pts.length - 1; i++) {
    const d = norm === 0
      ? Math.hypot(pts[i][0] - ax, pts[i][1] - ay)
      : Math.abs(dx * (pts[i][1] - ay) - dy * (pts[i][0] - ax)) / norm;
    if (d > best) { best = d; idx = i; }
  }
  if (best > eps) {
    const l = rdp(pts.slice(0, idx + 1), eps), r = rdp(pts.slice(idx), eps);
    return l.slice(0, -1).concat(r);
  }
  return [pts[0], pts[pts.length - 1]];
}

export function simplify(strokes) {
  return strokes.map((s) => rdp(s)).filter((s) => s.length > 0);
}

// Total ink length (sum of segment lengths inside strokes).
export function inkLength(strokes) {
  let t = 0;
  for (const s of strokes) for (let i = 1; i < s.length; i++) t += Math.hypot(s[i][0] - s[i - 1][0], s[i][1] - s[i - 1][1]);
  return t;
}

// Rasterize into a Float32Array(64*64) in [0,1] using a 2D canvas (white ink, black background).
const scratch = typeof document !== "undefined" ? document.createElement("canvas") : null;
if (scratch) { scratch.width = IMG; scratch.height = IMG; }
export function rasterize(strokes) {
  const ctx = scratch.getContext("2d", { willReadFrequently: true });
  ctx.fillStyle = "#000"; ctx.fillRect(0, 0, IMG, IMG);
  ctx.strokeStyle = "#fff"; ctx.fillStyle = "#fff";
  ctx.lineWidth = cfg.lineWidth; ctx.lineCap = "round"; ctx.lineJoin = "round";
  const k = (IMG - 1) / FRAME, o = 0.5;   // OpenCV pixel centres sit on integers, canvas centres at +0.5
  for (const s of strokes) {
    if (s.length === 1) { ctx.beginPath(); ctx.arc(s[0][0] * k + o, s[0][1] * k + o, 1, 0, Math.PI * 2); ctx.fill(); continue; }
    ctx.beginPath(); ctx.moveTo(s[0][0] * k + o, s[0][1] * k + o);
    for (let i = 1; i < s.length; i++) ctx.lineTo(s[i][0] * k + o, s[i][1] * k + o);
    ctx.stroke();
  }
  const data = ctx.getImageData(0, 0, IMG, IMG).data;
  const out = new Float32Array(IMG * IMG);
  for (let i = 0; i < out.length; i++) out[i] = data[i * 4] / 255;
  return out;
}

// Sequence features: x, y, dx*8, dy*8, new_stroke  (zero padded to MAX_PTS). Returns {seq, length}.
export function toSeq(strokes) {
  let pts = [];
  for (const s of strokes) s.forEach((p, i) => pts.push([p[0], p[1], i === 0 ? 1 : 0]));
  if (pts.length > MAX_PTS) {
    const keep = new Set();
    for (let i = 0; i < MAX_PTS; i++) keep.add(Math.round((i * (pts.length - 1)) / (MAX_PTS - 1)));
    pts = [...keep].sort((a, b) => a - b).map((i) => pts[i]);
  }
  const seq = new Float32Array(MAX_PTS * SEQ_FEATS);
  pts.forEach((p, i) => {
    const o = i * SEQ_FEATS;
    seq[o] = p[0] / FRAME; seq[o + 1] = p[1] / FRAME;
    if (i > 0 && !p[2]) { seq[o + 2] = (p[0] - pts[i - 1][0]) / FRAME * 8; seq[o + 3] = (p[1] - pts[i - 1][1]) / FRAME * 8; }
    seq[o + 4] = i === 0 ? 1 : p[2];
  });
  return { seq, length: Math.max(pts.length, 1) };
}

// Cut a stroke list at `frac` of its total ink (used by the replay of real QuickDraw sketches).
export function cutStrokes(strokes, frac) {
  const total = inkLength(strokes);
  let target = frac * total;
  const out = [];
  for (const s of strokes) {
    const part = [s[0]];
    for (let i = 1; i < s.length; i++) {
      const d = Math.hypot(s[i][0] - s[i - 1][0], s[i][1] - s[i - 1][1]);
      if (d >= target) {
        const t = d === 0 ? 0 : target / d;
        part.push([s[i - 1][0] + t * (s[i][0] - s[i - 1][0]), s[i - 1][1] + t * (s[i][1] - s[i - 1][1])]);
        out.push(part);
        return out;
      }
      target -= d; part.push(s[i]);
    }
    out.push(part);
  }
  return out;
}
