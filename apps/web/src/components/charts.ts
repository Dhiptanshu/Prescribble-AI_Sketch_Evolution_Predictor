// Tiny dependency-free canvas line chart (works offline, themed through CSS variables).
const PALETTE = ["#7c5cff", "#22d3ee", "#34d399", "#fbbf24", "#fb7185", "#a78bfa", "#f472b6"];
export const seriesColor = (i: number) => PALETTE[i % PALETTE.length]!;

export interface Series { name: string; color: string; points: [number, number][]; bold?: boolean; dots?: boolean }
export interface ChartOpts {
  xMax: number; yMax?: number; xTicks?: number;
  yFmt?: (v: number) => string; xFmt?: (v: number) => string;
}

const css = (n: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

export function drawLineChart(canvas: HTMLCanvasElement, series: Series[], o: ChartOpts) {
  const dpr = window.devicePixelRatio || 1, w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
  const ctx = canvas.getContext("2d")!;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const yMax = o.yMax ?? 1, yFmt = o.yFmt ?? ((v: number) => Math.round(v * 100) + "%"), xFmt = o.xFmt ?? ((v: number) => String(Math.round(v)));
  const pad = { l: 40, r: 12, t: 10, b: 24 }, iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
  const X = (v: number) => pad.l + (v / (o.xMax || 1)) * iw, Y = (v: number) => pad.t + ih - (v / yMax) * ih;
  ctx.font = "11.5px system-ui, sans-serif";
  ctx.fillStyle = css("--muted"); ctx.strokeStyle = "rgba(127,127,160,.22)"; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const v = (yMax * i) / 4;
    ctx.beginPath(); ctx.moveTo(pad.l, Y(v)); ctx.lineTo(w - pad.r, Y(v)); ctx.stroke();
    ctx.textAlign = "right"; ctx.fillText(yFmt(v), pad.l - 6, Y(v) + 4);
  }
  ctx.textAlign = "center";
  const ticks = o.xTicks ?? 4;
  for (let i = 0; i <= ticks; i++) { const v = (o.xMax * i) / ticks; ctx.fillText(xFmt(v), X(v), h - 6); }
  for (const s of series) {
    if (!s.points.length) continue;
    ctx.beginPath();
    s.points.forEach(([x, y], i) => (i ? ctx.lineTo(X(x), Y(y)) : ctx.moveTo(X(x), Y(y))));
    ctx.strokeStyle = s.color; ctx.lineWidth = s.bold ? 3 : 2; ctx.lineJoin = "round"; ctx.stroke();
    if (s.dots) for (const [x, y] of s.points) { ctx.beginPath(); ctx.arc(X(x), Y(y), 3, 0, 7); ctx.fillStyle = s.color; ctx.fill(); }
  }
}

/** Vertical bars (e.g. drawings per day). Labels are shown for the first, middle and last bar only. */
export function drawBarChart(canvas: HTMLCanvasElement, bars: { label: string; value: number }[], color = "#7c5cff") {
  const dpr = window.devicePixelRatio || 1, w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
  const ctx = canvas.getContext("2d")!;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const pad = { l: 28, r: 8, t: 8, b: 22 }, iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
  const max = Math.max(1, ...bars.map((b) => b.value));
  const top = max <= 4 ? max : Math.ceil(max / 4) * 4;
  ctx.font = "11.5px system-ui, sans-serif";
  ctx.strokeStyle = "rgba(127,127,160,.22)"; ctx.fillStyle = css("--muted"); ctx.lineWidth = 1; ctx.textAlign = "right";
  for (let i = 0; i <= 2; i++) {
    const v = Math.round((top * i) / 2), y = pad.t + ih - (v / top) * ih;
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w - pad.r, y); ctx.stroke();
    ctx.fillText(String(v), pad.l - 6, y + 4);
  }
  const slot = iw / Math.max(1, bars.length), bw = Math.max(2, slot * 0.7);
  bars.forEach((b, i) => {
    const bh = (b.value / top) * ih;
    ctx.fillStyle = b.value ? color : "rgba(127,127,160,.18)";
    ctx.fillRect(pad.l + i * slot + (slot - bw) / 2, pad.t + ih - Math.max(bh, b.value ? 1 : 2), bw, Math.max(bh, b.value ? 1 : 2));
  });
  ctx.fillStyle = css("--muted"); ctx.textAlign = "center";
  [0, Math.floor((bars.length - 1) / 2), bars.length - 1].forEach((i) => {
    const b = bars[i];
    if (b) ctx.fillText(b.label, Math.min(w - 18, Math.max(pad.l + 14, pad.l + i * slot + slot / 2)), h - 6);
  });
}
