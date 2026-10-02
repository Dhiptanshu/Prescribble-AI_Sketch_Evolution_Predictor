// Tiny dependency-free canvas line chart (works offline). Series: [{name, color, points:[[x,y],...], dashed?}]
const PALETTE = ["#7c5cff", "#22d3ee", "#34d399", "#fbbf24", "#fb7185", "#a78bfa", "#f472b6"];
export const color = (i) => PALETTE[i % PALETTE.length];

const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

export function lineChart(canvas, series, { xMax, yMax = 1, xLabel = "", yFmt = (v) => Math.round(v * 100) + "%", xFmt = (v) => v, xTicks = 4 } = {}) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  const pad = { l: 40, r: 12, t: 10, b: 24 };
  const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
  const X = (v) => pad.l + (v / (xMax || 1)) * iw;
  const Y = (v) => pad.t + ih - (v / yMax) * ih;
  ctx.font = "11.5px system-ui, sans-serif";
  ctx.fillStyle = css("--muted"); ctx.strokeStyle = "rgba(127,127,160,.22)"; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const v = (yMax * i) / 4;
    ctx.beginPath(); ctx.moveTo(pad.l, Y(v)); ctx.lineTo(w - pad.r, Y(v)); ctx.stroke();
    ctx.textAlign = "right"; ctx.fillText(yFmt(v), pad.l - 6, Y(v) + 4);
  }
  ctx.textAlign = "center";
  for (let i = 0; i <= xTicks; i++) {
    const v = (xMax * i) / xTicks;
    ctx.fillText(xFmt(v), X(v), h - 6);
  }
  series.forEach((s) => {
    if (!s.points.length) return;
    ctx.beginPath();
    s.points.forEach(([x, y], i) => (i ? ctx.lineTo(X(x), Y(y)) : ctx.moveTo(X(x), Y(y))));
    ctx.strokeStyle = s.color; ctx.lineWidth = s.bold ? 3 : 2; ctx.lineJoin = "round";
    ctx.setLineDash(s.dashed ? [5, 4] : []); ctx.stroke(); ctx.setLineDash([]);
    s.points.forEach(([x, y]) => { if (s.dots) { ctx.beginPath(); ctx.arc(X(x), Y(y), 3, 0, 7); ctx.fillStyle = s.color; ctx.fill(); } });
  });
}
