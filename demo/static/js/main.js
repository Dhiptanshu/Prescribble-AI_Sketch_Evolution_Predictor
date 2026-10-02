import { Board } from "./board.js";
import { SketchModel } from "./model.js";
import { lineChart, color } from "./charts.js";
import { Challenge, Replay } from "./modes.js";
import { IMG } from "./pipeline.js";

const $ = (s) => document.querySelector(s);
const model = new SketchModel();
const state = { history: [], last: null, busy: false, dirty: false, ghost: true, metric: "top5", results: null, truth: null };

// ---------- theme ----------
const root = document.documentElement;
let saved = null;
try { saved = localStorage.getItem("theme"); } catch {}   // storage can be blocked on locked-down lab browsers
root.dataset.theme = saved || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
$("#theme").onclick = () => {
  root.dataset.theme = root.dataset.theme === "light" ? "dark" : "light";
  try { localStorage.setItem("theme", root.dataset.theme); } catch {}
  board.render(); drawTimeline(); drawResults(); paintGhost();
};

// ---------- panels ----------
const bars = $("#bars"), top1El = $("#top1");
for (let i = 0; i < 5; i++) bars.insertAdjacentHTML("beforeend", `<li><span class="nm">–</span><div class="track"><div class="fill"></div></div><span class="pc"></span></li>`);

function renderPrediction(r) {
  if (!r) {
    top1El.innerHTML = `<span class="label">Waiting for a stroke</span>`;
    [...bars.children].forEach((li) => { li.querySelector(".nm").textContent = "–"; li.querySelector(".fill").style.width = "0"; li.querySelector(".pc").textContent = ""; li.classList.remove("truth"); });
    $("#certainty").textContent = "—";
    return;
  }
  const t = r.top5[0];
  top1El.innerHTML = `<span class="name">${t.name}</span><span class="pct">${(t.p * 100).toFixed(0)}%</span>`;
  r.top5.forEach((c, i) => {
    const li = bars.children[i];
    li.querySelector(".nm").textContent = c.name;
    li.querySelector(".fill").style.width = (c.p * 100).toFixed(1) + "%";
    li.querySelector(".pc").textContent = (c.p * 100).toFixed(0) + "%";
    li.classList.toggle("truth", state.truth === c.name);
  });
  const sure = 1 - r.entropy;
  $("#certainty").textContent = `certainty ${(sure * 100).toFixed(0)}% · ${r.ms.toFixed(0)} ms`;
}

// ---------- ghost (the model's real completion output, drawn in the accent colour) ----------
const ghostCanvas = $("#ghost"), gctx = ghostCanvas.getContext("2d");
function paintGhost() {
  gctx.clearRect(0, 0, IMG, IMG);
  ghostCanvas.style.opacity = state.ghost ? 1 : 0;
  if (!state.last || !state.ghost) return;
  const id = gctx.createImageData(IMG, IMG), g = state.last.ghost, ink = state.last.img;
  const drawn = (x, y) => {   // is there already ink within 2 px? then the ghost stays out of the way
    for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) {
      const xx = x + dx, yy = y + dy;
      if (xx >= 0 && yy >= 0 && xx < IMG && yy < IMG && ink[yy * IMG + xx] > 0.2) return true;
    }
    return false;
  };
  for (let y = 0; y < IMG; y++) for (let x = 0; x < IMG; x++) {
    const i = y * IMG + x;
    const v = drawn(x, y) ? 0 : Math.max(0, Math.min(1, (g[i] - 0.15) / 0.6));   // only the predicted *remaining* ink; ignore faint haze
    id.data[i * 4] = 124; id.data[i * 4 + 1] = 92; id.data[i * 4 + 2] = 255; id.data[i * 4 + 3] = v * 170;
  }
  gctx.putImageData(id, 0, 0);
}
$("#ghost-toggle").onchange = (e) => { state.ghost = e.target.checked; paintGhost(); };

// ---------- timeline ----------
function drawTimeline() {
  const h = state.history, canvas = $("#timeline"), legend = $("#timeline-legend");
  if (!h.length) { lineChart(canvas, [], { xMax: 1 }); legend.innerHTML = ""; return; }
  const last = h[h.length - 1];
  const idx = last.order.slice(0, 3);
  const series = idx.map((c, i) => ({ name: model.classes[c], color: color(i), bold: i === 0, points: h.map((s) => [s.ink, s.probs[c]]) }));
  lineChart(canvas, series, { xMax: Math.max(last.ink, 60), xFmt: (v) => Math.round(v) });
  legend.innerHTML = series.map((s) => `<span><i style="background:${s.color}"></i>${s.name}</span>`).join("");
}

// ---------- prediction loop (latest drawing wins; never queues stale work) ----------
async function predict(record) {
  if (state.busy) { state.dirty = true; return; }
  state.busy = true;
  try {
    do {
      state.dirty = false;
      const r = await model.predict(board.strokes);
      state.last = r;
      if (r) {
        const ink = board.ink, prev = state.history[state.history.length - 1];
        const rec = { ink, probs: r.probs, order: r.top5.map((c) => c.idx), top5: r.top5 };
        if (!prev || record || ink - prev.ink > 6) state.history.push(rec); else state.history[state.history.length - 1] = rec;
        modes.current?.onPrediction?.(r, board);
      } else state.history = [];
      renderPrediction(r); paintGhost(); drawTimeline();
      $("#chip-latency").hidden = false;
      if (r) $("#chip-latency").textContent = `${r.ms.toFixed(1)} ms / prediction`;
    } while (state.dirty);
  } finally { state.busy = false; }
}

// ---------- board ----------
const board = new Board($("#draw"), (ev) => {
  $("#hint").classList.toggle("hide", board.strokes.length > 0);
  const n = board.strokes.length;
  $("#ink-meta").textContent = `${n} stroke${n === 1 ? "" : "s"} · ${Math.round(board.ink)} px ink`;
  if (ev === "clear") { state.history = []; state.last = null; renderPrediction(null); paintGhost(); drawTimeline(); modes.current?.onClear?.(); return; }
  if (!board.strokes.length) { state.history = []; state.last = null; renderPrediction(null); paintGhost(); drawTimeline(); return; }
  predict(ev === "end" || ev === "undo" || ev === "start");
});
$("#clear").onclick = () => board.clear();
$("#undo").onclick = () => board.undo();

// ---------- modes ----------
const ui = { $, board, model, state, predict, renderPrediction, drawTimeline };
const modes = { current: null, free: null, challenge: new Challenge(ui), replay: new Replay(ui) };
function setMode(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.mode === name));
  modes.current?.stop?.();
  board.locked = false; state.truth = null; board.clear();
  $("#progress").firstElementChild.style.width = "0";
  const panel = $("#mode-panel");
  panel.hidden = name === "free"; panel.innerHTML = "";
  $("#banner").innerHTML = name === "free" ? "Draw anything from the list. The purple ghost is the model’s own prediction of how your drawing will end." : "";
  modes.current = modes[name] || null;
  modes.current?.start?.(panel);
}
document.querySelectorAll(".tab").forEach((t) => (t.onclick = () => setMode(t.dataset.mode)));

// ---------- results (read from real training runs) ----------
const LABELS = { mlp: "MLP (NumPy)", cnn: "CNN", lstm: "LSTM", fusion: "CNN + LSTM", fusion_ghost: "CNN + LSTM + ghost", resnet_ghost: "ResNet18 + LSTM + ghost" };
function drawResults() {
  const r = state.results, table = $("#results-table");
  if (!r || !Object.keys(r).length) { table.innerHTML = `<p class="empty">No training results found yet.</p>`; lineChart($("#acc-chart"), [], { xMax: 100 }); return; }
  const names = Object.keys(r);
  const keys = Object.keys(r[names[0]]).sort((a, b) => Number(a) - Number(b));   // JSON keys: "0.1" ... "1.0"
  const live = model.meta?.model, m = state.metric;
  const series = names.map((n, i) => ({ name: n, color: color(i), dots: true, bold: n === live, points: keys.map((k) => [Number(k) * 100, r[n][k][m]]) }));
  lineChart($("#acc-chart"), series, { xMax: 100, xFmt: (v) => v + "%" });
  const bestAt = Object.fromEntries(keys.map((k) => [k, Math.max(...names.map((n) => r[n][k][m]))]));
  table.innerHTML = `<table><thead><tr><th>Model</th>${keys.map((k) => `<th>${Math.round(Number(k) * 100)}%</th>`).join("")}</tr></thead><tbody>` +
    names.map((n, i) => `<tr><td><i style="display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:7px;background:${color(i)}"></i>${LABELS[n] || n}${n === live ? " ★" : ""}</td>` +
      keys.map((k) => `<td${r[n][k][m] === bestAt[k] ? ' style="color:var(--good);font-weight:650"' : ""}>${(r[n][k][m] * 100).toFixed(1)}</td>`).join("") + `</tr>`).join("") +
    `</tbody></table><p class="meta" style="margin-top:10px">${m === "top5" ? "Top-5" : "Top-1"} accuracy (%) at each fraction of the sketch’s ink · ★ = model running in this page · green = best at that fraction</p>`;
}
document.querySelectorAll("#metric-toggle button").forEach((b) => (b.onclick = () => {
  document.querySelectorAll("#metric-toggle button").forEach((x) => x.classList.toggle("active", x === b));
  state.metric = b.dataset.m; drawResults();
}));
window.addEventListener("resize", () => { drawTimeline(); drawResults(); });

// ---------- boot ----------
(async () => {
  const chip = $("#chip-model");
  try {
    await model.load();
    chip.classList.add("ok");
    chip.lastElementChild.textContent = `${LABELS[model.meta.model] || model.meta.model} · ${model.meta.size_mb.toFixed(1)} MB · runs in your browser`;
  } catch (e) {
    chip.classList.add("err"); chip.lastElementChild.textContent = "model failed to load";
    console.error(e);
  }
  try { state.results = await (await fetch("models/results.json")).json(); } catch { state.results = null; }
  setMode("free"); drawTimeline(); drawResults();
})();
