// Styles live inside the widget's shadow root, so they can neither leak into nor be broken by the host page.
export const STYLES = `
:host { display: inline-block; max-width: 100%; }
.root { --bg: #ffffff; --paper: #fbfbfe; --ink: #141833; --muted: #646a86; --border: rgba(20,24,50,.14); --accent: #7c5cff; --accent2: #22d3ee;
  font: 14px/1.4 system-ui, -apple-system, "Segoe UI", Roboto, Ubuntu, sans-serif; color: var(--ink); width: var(--size); max-width: 100%; }
.root[data-theme="dark"] { --bg: #10131d; --paper: #0f1220; --ink: #f5f6fb; --muted: #959ab1; --border: rgba(255,255,255,.14); }
.frame { position: relative; width: 100%; aspect-ratio: 1; border-radius: 14px; overflow: hidden; background: var(--paper); border: 1px solid var(--border); touch-action: none; }
.frame::before { content: ""; position: absolute; inset: 0; background-image: radial-gradient(rgba(127,127,160,.25) 1px, transparent 1px); background-size: 22px 22px; pointer-events: none; }
canvas { position: absolute; inset: 0; width: 100%; height: 100%; }
canvas.draw { cursor: crosshair; touch-action: none; }
.hint { position: absolute; left: 0; right: 0; bottom: 12px; text-align: center; color: var(--muted); font-size: 13px; pointer-events: none; transition: opacity .25s; padding: 0 16px; }
.hint.hide { opacity: 0; }
.guesses { margin-top: 10px; padding: 10px 12px; border-radius: 12px; background: var(--bg); border: 1px solid var(--border); }
.top { font-weight: 750; font-size: 20px; letter-spacing: -.01em; margin-bottom: 6px; min-height: 28px; }
.top small { font-weight: 500; font-size: 13px; color: var(--muted); margin-left: 6px; }
.row { display: grid; grid-template-columns: 84px 1fr 38px; gap: 8px; align-items: center; font-size: 12.5px; margin-top: 4px; }
.row .track { height: 7px; border-radius: 99px; background: rgba(127,127,160,.2); overflow: hidden; }
.row .fill { height: 100%; width: 0; border-radius: 99px; background: linear-gradient(90deg, var(--accent), var(--accent2)); transition: width .15s ease-out; }
.row .pc { text-align: right; color: var(--muted); font-variant-numeric: tabular-nums; }
.row .nm { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bar { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; font-size: 12px; color: var(--muted); }
button { font: inherit; color: var(--ink); background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 4px 10px; cursor: pointer; }
button:hover { border-color: var(--accent); }
a { color: var(--muted); }
.status { color: var(--muted); font-size: 12.5px; }
`;
