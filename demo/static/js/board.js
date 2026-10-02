// Drawing surface. Keeps strokes in the model's fixed 0..255 frame no matter how big the canvas is on screen.
import { FRAME, inkLength } from "./pipeline.js";

export class Board {
  constructor(canvas, onChange) {
    this.canvas = canvas; this.ctx = canvas.getContext("2d"); this.onChange = onChange;
    this.strokes = []; this.drawing = false; this.locked = false;
    new ResizeObserver(() => this.resize()).observe(canvas.parentElement);
    canvas.addEventListener("pointerdown", (e) => this.down(e));
    canvas.addEventListener("pointermove", (e) => this.move(e));
    for (const t of ["pointerup", "pointercancel", "pointerleave"]) canvas.addEventListener(t, (e) => this.up(e));
    this.resize();
  }
  resize() {
    const dpr = window.devicePixelRatio || 1, r = this.canvas.getBoundingClientRect();
    this.canvas.width = r.width * dpr; this.canvas.height = r.height * dpr; this.px = r.width; this.render();
  }
  pos(e) {
    const r = this.canvas.getBoundingClientRect();
    const clamp = (v) => Math.min(FRAME, Math.max(0, v));
    return [clamp(((e.clientX - r.left) / r.width) * FRAME), clamp(((e.clientY - r.top) / r.height) * FRAME)];
  }
  down(e) {
    if (this.locked) return;
    this.canvas.setPointerCapture(e.pointerId);
    this.drawing = true; this.strokes.push([this.pos(e)]); this.render(); this.onChange("start");
  }
  move(e) {
    if (!this.drawing) return;
    const s = this.strokes[this.strokes.length - 1], p = this.pos(e), q = s[s.length - 1];
    if (Math.hypot(p[0] - q[0], p[1] - q[1]) < 0.8) return;
    s.push(p); this.render(); this.onChange("move");
  }
  up() {
    if (!this.drawing) return;
    this.drawing = false; this.onChange("end");
  }
  set(strokes) { this.strokes = strokes; this.render(); }
  clear() { this.strokes = []; this.render(); this.onChange("clear"); }
  undo() { this.strokes.pop(); this.render(); this.onChange("undo"); }
  get ink() { return inkLength(this.strokes); }
  render() {
    const dpr = window.devicePixelRatio || 1, ctx = this.ctx, k = (this.canvas.width / FRAME);
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue("--ink").trim();
    ctx.fillStyle = ctx.strokeStyle; ctx.lineWidth = 4.5 * dpr; ctx.lineCap = "round"; ctx.lineJoin = "round";
    for (const s of this.strokes) {
      if (s.length === 1) { ctx.beginPath(); ctx.arc(s[0][0] * k, s[0][1] * k, 2.25 * dpr, 0, 7); ctx.fill(); continue; }
      ctx.beginPath(); ctx.moveTo(s[0][0] * k, s[0][1] * k);
      for (let i = 1; i < s.length; i++) ctx.lineTo(s[i][0] * k, s[i][1] * k);
      ctx.stroke();
    }
  }
}
