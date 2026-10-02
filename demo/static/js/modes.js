// Interactive modes built on the same real model: an AI challenge and a replay of real QuickDraw test sketches.
import { cutStrokes, inkLength } from "./pipeline.js";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export class Challenge {
  constructor(ui) { this.ui = ui; this.stats = { rounds: 0, wins: 0, strokes: [] }; this.round = null; }

  start(panel) {
    this.panel = panel;
    panel.innerHTML = `
      <div class="card-head"><h2>AI challenge</h2><span class="meta">you vs the model</span></div>
      <div class="panel-row"><div class="target" id="ch-target">—</div>
        <div><button class="btn primary" id="ch-new">New word</button> <button class="btn" id="ch-giveup">Give up</button></div></div>
      <div id="ch-result"></div>
      <div class="scoreboard"><div><b id="ch-rounds">0</b><span>rounds</span></div><div><b id="ch-wins">0</b><span>AI got it</span></div><div><b id="ch-avg">–</b><span>avg strokes needed</span></div></div>`;
    panel.querySelector("#ch-new").onclick = () => this.newRound();
    panel.querySelector("#ch-giveup").onclick = () => this.finish(false);
    this.newRound();
  }
  stop() { this.round = null; }

  newRound() {
    const { model, board, state, $ } = this.ui;
    const names = model.classes;
    const target = names[Math.floor(Math.random() * names.length)];
    this.round = { target, active: true };
    state.truth = null;
    board.locked = false; board.clear();
    $("#banner").innerHTML = `Draw a <b>${target}</b>. The AI wins if it recognises it (≥ 50% confidence) before you finish.`;
    this.panel.querySelector("#ch-target").textContent = target;
    this.panel.querySelector("#ch-result").innerHTML = "";
  }
  onClear() { /* round stays active */ }

  onPrediction(r, board) {
    const rd = this.round;
    if (!rd?.active) return;
    const t = r.top5[0];
    if (t.name === rd.target && t.p >= 0.5) this.finish(true, r, board);
  }

  finish(won, r, board) {
    const rd = this.round;
    if (!rd?.active) return;
    rd.active = false;
    const { board: b, state } = this.ui;
    b.locked = true;
    const strokes = b.strokes.length, ink = Math.round(b.ink);
    this.stats.rounds++;
    let msg;
    if (won) { this.stats.wins++; this.stats.strokes.push(strokes); msg = `<div class="toast">The AI recognised <b>${rd.target}</b> after ${strokes} stroke${strokes === 1 ? "" : "s"} (${ink} px of ink).</div>`; }
    else {
      const t = state.last?.top5?.[0];
      msg = `<div class="toast bad">The AI did not get it. ${t ? `Its best guess was <b>${t.name}</b> (${(t.p * 100).toFixed(0)}%).` : "Nothing was drawn."}</div>`;
    }
    this.panel.querySelector("#ch-result").innerHTML = msg;
    this.panel.querySelector("#ch-rounds").textContent = this.stats.rounds;
    this.panel.querySelector("#ch-wins").textContent = this.stats.wins;
    const s = this.stats.strokes;
    this.panel.querySelector("#ch-avg").textContent = s.length ? (s.reduce((a, c) => a + c, 0) / s.length).toFixed(1) : "–";
  }
}

export class Replay {
  constructor(ui) { this.ui = ui; this.samples = null; this.playing = false; }

  async start(panel) {
    this.panel = panel;
    if (!this.samples) {
      try { this.samples = await (await fetch("models/samples.json")).json(); } catch { this.samples = []; }
    }
    if (!this.samples.length) { panel.innerHTML = `<p class="empty">No sample sketches found (run <code>python -m src.export.samples</code>).</p>`; return; }
    const labels = [...new Set(this.samples.map((s) => s.label))];
    panel.innerHTML = `
      <div class="card-head"><h2>Real QuickDraw test sketches</h2><span class="meta">never seen in training</span></div>
      <div class="panel-row"><select id="rp-class">${labels.map((l) => `<option>${l}</option>`).join("")}</select>
        <button class="btn" id="rp-shuffle">Another sketch</button>
        <button class="btn primary" id="rp-play">▶ Play</button></div>
      <div id="rp-result"></div>`;
    panel.querySelector("#rp-class").onchange = () => this.pick();
    panel.querySelector("#rp-shuffle").onclick = () => this.pick();
    panel.querySelector("#rp-play").onclick = () => this.play();
    this.pick();
  }
  stop() { this.playing = false; }

  pick() {
    const label = this.panel.querySelector("#rp-class").value;
    const pool = this.samples.filter((s) => s.label === label);
    this.sample = pool[Math.floor(Math.random() * pool.length)];
    const { board, state, $ } = this.ui;
    this.playing = false;
    state.truth = this.sample.label;
    board.clear(); board.set([]);
    $("#banner").innerHTML = `Ground truth: <b>${this.sample.label}</b>. Press play to watch the model guess as the sketch is drawn.`;
    this.panel.querySelector("#rp-result").innerHTML = "";
    $("#progress").firstElementChild.style.width = "0";
  }

  async play() {
    const { board, state, predict, $ } = this.ui;
    if (this.playing) { this.playing = false; return; }
    this.playing = true;
    board.clear(); state.truth = this.sample.label;
    const steps = 50, trace = [];
    for (let i = 1; i <= steps && this.playing; i++) {
      const frac = i / steps;
      board.set(cutStrokes(this.sample.strokes, frac));
      $("#ink-meta").textContent = `${board.strokes.length} stroke${board.strokes.length === 1 ? "" : "s"} · ${Math.round(board.ink)} px ink`;
      $("#hint").classList.add("hide");
      $("#progress").firstElementChild.style.width = frac * 100 + "%";
      await predict(i === 1 || i % 5 === 0);
      const top = state.last?.top5 ?? [];
      trace.push({ frac, top1: top[0]?.name === state.truth, top5: top.some((c) => c.name === state.truth) });
      await sleep(70);
    }
    if (this.playing) this.summarise(trace);
    this.playing = false;
  }

  // Earliest completion fraction from which the answer stays correct until the end.
  summarise(trace) {
    const stable = (key) => { let i = trace.length; while (i > 0 && trace[i - 1][key]) i--; return i < trace.length ? trace[i].frac : null; };
    const t1 = stable("top1"), t5 = stable("top5");
    const fmt = (f) => (f == null ? "never" : Math.round(f * 100) + "% of the ink");
    this.panel.querySelector("#rp-result").innerHTML =
      `<div class="toast ${t5 == null ? "bad" : ""}">Correct in Top-5 (and staying correct) from <b>${fmt(t5)}</b>; as the #1 guess from <b>${fmt(t1)}</b>.</div>`;
  }
}
