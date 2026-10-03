import { SketchModel, type Prediction } from "@prescribble/engine";
import { ghostPixels } from "@prescribble/engine/ghost";
import { FRAME, IMG, inkLength, type Stroke } from "@prescribble/engine/pipeline";
import { STYLES } from "./styles";
import { assetsBaseFrom, clampSize, resolveTheme, resolveVersion, toGuesses, type Guess, type ThemeOption } from "./util";

export interface GuessEvent { top5: Guess[]; ink: number; strokes: Stroke[] }

export interface MountOptions {
  /** Square size in CSS pixels (200 to 800). Default 360. */
  size?: number;
  theme?: ThemeOption;
  showGuesses?: boolean;
  showGhost?: boolean;
  /** Where models/ and ort/ are served from. Default: the host that served this script. */
  assetsBase?: string;
  /** Model version folder under models/. Default: the live version named in models/registry.json (so a promoted model reaches every page). */
  model?: string;
  onReady?: (info: { classes: string[] }) => void;
  onGuess?: (event: GuessEvent) => void;
  onError?: (error: Error) => void;
}

export interface WidgetHandle {
  clear(): void;
  undo(): void;
  getStrokes(): Stroke[];
  setTheme(theme: ThemeOption): void;
  destroy(): void;
}

/** Set by index.ts from document.currentScript when the script loads (it is null afterwards). */
export const scriptSource: { src: string | null } = { src: null };

// One model per page, however many widgets are mounted.
const models = new Map<string, Promise<SketchModel>>();
function loadModel(base: string, version: string): Promise<SketchModel> {
  const key = `${base}|${version}`;
  let p = models.get(key);
  if (!p) {
    p = SketchModel.load({ modelBase: `${base}models/${version}/`, wasmBase: `${base}ort/` });
    p.catch(() => models.delete(key));                 // allow a retry after a network failure
    models.set(key, p);
  }
  return p;
}

const el = <K extends keyof HTMLElementTagNameMap>(tag: K, className?: string, text?: string) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

export function mount(target: string | Element, options: MountOptions = {}): WidgetHandle {
  const host = typeof target === "string" ? document.querySelector(target) : target;
  if (!host) throw new Error(`Prescribble: no element matches "${String(target)}"`);
  if (host.shadowRoot) throw new Error("Prescribble: this element already has a widget mounted on it");
  const opts = { showGuesses: true, showGhost: true, ...options };
  const base = assetsBaseFrom(scriptSource.src, opts.assetsBase);

  const shadow = host.attachShadow({ mode: "open" });
  const style = el("style"); style.textContent = STYLES;
  const root = el("div", "root");
  root.style.setProperty("--size", `${clampSize(opts.size)}px`);
  const media = matchMedia("(prefers-color-scheme: dark)");
  const applyTheme = (t: ThemeOption | undefined) => { root.dataset.theme = resolveTheme(t, media.matches); };
  let theme = opts.theme;
  applyTheme(theme);
  const onMedia = () => applyTheme(theme);
  media.addEventListener("change", onMedia);

  const frame = el("div", "frame");
  const ghostCanvas = el("canvas", "ghost"); ghostCanvas.width = IMG; ghostCanvas.height = IMG; ghostCanvas.setAttribute("aria-hidden", "true");
  const canvas = el("canvas", "draw"); canvas.setAttribute("role", "img"); canvas.setAttribute("aria-label", "Drawing canvas: draw and the AI guesses what it is");
  const hint = el("div", "hint", "Loading the model…");
  frame.append(ghostCanvas, canvas, hint);
  root.append(frame);

  const rows: { nm: HTMLElement; fill: HTMLElement; pc: HTMLElement }[] = [];
  let topLine: HTMLElement | null = null;
  if (opts.showGuesses) {
    const box = el("div", "guesses"); box.setAttribute("aria-live", "polite");
    topLine = el("div", "top", "…");
    box.append(topLine);
    for (let i = 0; i < 5; i++) {
      const row = el("div", "row"), nm = el("span", "nm", "–"), track = el("div", "track"), fill = el("div", "fill"), pc = el("span", "pc");
      track.append(fill); row.append(nm, track, pc); box.append(row); rows.push({ nm, fill, pc });
    }
    root.append(box);
  }
  const bar = el("div", "bar");
  const clearBtn = el("button", undefined, "Clear"); clearBtn.type = "button";
  bar.append(el("span", "status", "Runs in your browser"), clearBtn);
  root.append(bar);
  shadow.append(style, root);

  // ---------------------------------------------------------------- drawing (strokes live in the model's 0..255 frame)
  let strokes: Stroke[] = [];
  let drawing = false;
  let model: SketchModel | null = null;
  const abort = new AbortController();
  const { signal } = abort;

  const paint = () => {
    const dpr = window.devicePixelRatio || 1, ctx = canvas.getContext("2d")!, k = canvas.width / FRAME;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const color = getComputedStyle(root).getPropertyValue("--ink").trim() || "#000";
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 4.5 * dpr; ctx.lineCap = "round"; ctx.lineJoin = "round";
    for (const s of strokes) {
      const first = s[0]; if (!first) continue;
      if (s.length === 1) { ctx.beginPath(); ctx.arc(first[0] * k, first[1] * k, 2.25 * dpr, 0, 7); ctx.fill(); continue; }
      ctx.beginPath(); ctx.moveTo(first[0] * k, first[1] * k);
      for (let i = 1; i < s.length; i++) ctx.lineTo(s[i]![0] * k, s[i]![1] * k);
      ctx.stroke();
    }
  };
  const fit = () => {
    const dpr = window.devicePixelRatio || 1, r = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(r.width * dpr)); canvas.height = Math.max(1, Math.round(r.height * dpr));
    paint();
  };
  const ro = new ResizeObserver(fit);
  ro.observe(frame);

  const showGuesses = (p: Prediction | null) => {
    if (topLine) {
      topLine.replaceChildren();
      if (p) { topLine.append(document.createTextNode(p.top5[0]!.name)); topLine.append(el("small", undefined, `${Math.round(p.top5[0]!.p * 100)}%`)); }
      else topLine.textContent = "Draw something";
      rows.forEach((r, i) => {
        const g = p?.top5[i];
        r.nm.textContent = g?.name ?? "–"; r.fill.style.width = g ? `${(g.p * 100).toFixed(1)}%` : "0%"; r.pc.textContent = g ? `${Math.round(g.p * 100)}%` : "";
      });
    }
    const gctx = ghostCanvas.getContext("2d")!;
    gctx.clearRect(0, 0, IMG, IMG);
    if (p && opts.showGhost) { const img = gctx.createImageData(IMG, IMG); img.data.set(ghostPixels(p)); gctx.putImageData(img, 0, 0); }
  };

  // latest drawing wins: never queue stale predictions
  let busy = false;
  let pending: Stroke[] | null = null;
  const predict = async (s: Stroke[]) => {
    pending = s;
    if (busy || !model) return;
    busy = true;
    try {
      while (pending) {
        const job: Stroke[] = pending; pending = null;
        const p = job.length ? await model.predict(job) : null;
        if (signal.aborted) return;
        showGuesses(p);
        if (p) opts.onGuess?.({ top5: toGuesses(p.top5), ink: Math.round(inkLength(job)), strokes: job.map((x) => x.map(([a, b]) => [a, b] as [number, number])) });
      }
    } catch (e) {
      opts.onError?.(e instanceof Error ? e : new Error(String(e)));
    } finally {
      busy = false;
    }
  };

  const pos = (e: PointerEvent): [number, number] => {
    const r = canvas.getBoundingClientRect(), clamp = (v: number) => Math.min(FRAME, Math.max(0, v));
    return [clamp(((e.clientX - r.left) / r.width) * FRAME), clamp(((e.clientY - r.top) / r.height) * FRAME)];
  };
  const changed = () => { hint.classList.toggle("hide", strokes.length > 0); paint(); void predict(strokes.map((s) => s.slice())); };
  canvas.addEventListener("pointerdown", (e) => {
    canvas.setPointerCapture(e.pointerId); drawing = true; strokes = [...strokes, [pos(e)]]; changed();
  }, { signal });
  canvas.addEventListener("pointermove", (e) => {
    if (!drawing) return;
    const s = strokes[strokes.length - 1]!, p = pos(e), q = s[s.length - 1]!;
    if (Math.hypot(p[0] - q[0], p[1] - q[1]) < 0.8) return;
    s.push(p); changed();
  }, { signal });
  for (const type of ["pointerup", "pointercancel"] as const) canvas.addEventListener(type, () => { drawing = false; }, { signal });

  const clear = () => { strokes = []; changed(); showGuesses(null); };
  const undo = () => { strokes = strokes.slice(0, -1); changed(); if (!strokes.length) showGuesses(null); };
  clearBtn.addEventListener("click", clear, { signal });
  showGuesses(null);

  resolveVersion(base, opts.model).then((version) => loadModel(base, version)).then((m) => {
    if (signal.aborted) return;
    model = m;
    hint.textContent = "Draw anything. The AI guesses as you go.";
    opts.onReady?.({ classes: m.classes });
    if (strokes.length) void predict(strokes.map((s) => s.slice()));
  }).catch((e) => {
    hint.textContent = "Could not load the model.";
    opts.onError?.(e instanceof Error ? e : new Error(String(e)));
  });

  return {
    clear, undo,
    getStrokes: () => strokes.map((s) => s.map(([a, b]) => [a, b] as [number, number])),
    setTheme: (t) => { theme = t; applyTheme(t); paint(); },
    destroy: () => { abort.abort(); ro.disconnect(); media.removeEventListener("change", onMedia); shadow.replaceChildren(); },
  };
}
