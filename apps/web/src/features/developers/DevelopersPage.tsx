import { useState } from "react";
import { CodeBlock } from "../../components/CodeBlock";
import { useAuth } from "../../lib/auth";
import { useModelInfo } from "../../lib/platform";
import { ERRORS, EXAMPLE_REQUEST, EXAMPLE_RESPONSE, elementSnippet, snippets, widgetSnippet } from "./docsExamples";
import { KeysManager } from "./KeysManager";
import { WidgetDemo } from "./WidgetDemo";

const LANGS = [["curl", "cURL"], ["python", "Python"], ["node", "Node.js"]] as const;

const WIDGET_OPTIONS: [string, string, string][] = [
  ["size", "360", "Width and height in pixels (200 to 800)."],
  ["theme", '"auto"', '"light", "dark" or "auto" (follows the visitor).'],
  ["showGuesses", "true", "Show the Top-5 list under the canvas."],
  ["showGhost", "true", "Paint the model's prediction of how the drawing will end."],
  ["onGuess", "-", "Called after every stroke: { top5: [{ label, probability }], ink, strokes }."],
  ["onReady / onError", "-", "Model loaded, or something failed (network, unsupported browser)."],
];

export function DevelopersPage() {
  const { backend } = useAuth();
  const origin = window.location.origin;
  const info = useModelInfo();
  const [lang, setLang] = useState<(typeof LANGS)[number][0]>("curl");
  const code = snippets(origin)[lang];
  const limits = info.data?.limits;

  return (
    <div className="docs">
      <div className="page-head"><h1>Build with Prescribble</h1></div>
      <p className="lead-docs">Two ways to add “the AI that guesses your drawing” to your product. Pick the one that fits.</p>

      <div className="grid3 two">
        <div className="card feature"><h3>The widget</h3><p>One script tag. The model runs <b>inside your visitor’s browser</b>, so drawings never leave their device and there is nothing to host, meter or secure. No key needed.</p></div>
        <div className="card feature"><h3>The REST API</h3><p>For backends, mobile apps and other languages. Send strokes, get ranked guesses. Authenticated with a secret key, metered and rate limited.</p></div>
      </div>

      <section className="card" id="widget" aria-label="Widget">
        <div className="card-head"><h2>Widget</h2><span className="meta">no key · runs in the browser</span></div>
        <p className="meta" style={{ marginBottom: 12 }}>Add this to any page:</p>
        <CodeBlock code={widgetSnippet(origin)} label="Widget embed code" />
        <p className="meta" style={{ margin: "14px 0 10px" }}>Try it. This is the real script, loaded the same way your page would load it:</p>
        <WidgetDemo />
        <h3 className="sub-h">Or as an HTML element</h3>
        <CodeBlock code={elementSnippet(origin)} label="Custom element embed code" />
        <h3 className="sub-h">Options</h3>
        <table aria-label="Widget options">
          <thead><tr><th>Option</th><th>Default</th><th>What it does</th></tr></thead>
          <tbody>{WIDGET_OPTIONS.map(([o, d, w]) => <tr key={o}><td><code>{o}</code></td><td><code>{d}</code></td><td>{w}</td></tr>)}</tbody>
        </table>
        <p className="meta" style={{ marginTop: 12 }}>
          The returned handle has <code>clear()</code>, <code>undo()</code>, <code>getStrokes()</code>, <code>setTheme()</code> and <code>destroy()</code>.
          The script is about 60 kB; the model (about 18 MB) and runtime load once and are cached by the browser.
          Privacy: the drawing is processed on the visitor’s device. The widget makes no request that carries it.
        </p>
      </section>

      <section className="card" id="api" aria-label="REST API">
        <div className="card-head"><h2>REST API</h2><span className="meta">secret key · server to server</span></div>
        <p className="meta" style={{ marginBottom: 12 }}>
          <code>POST {origin}/api/v1/predict</code> with a drawing as strokes in a 256 by 256 frame (<code>[[x, y], …]</code> per stroke).
          Send a partial drawing to get a partial-drawing guess. Authenticate with <code>Authorization: Bearer &lt;key&gt;</code> or <code>X-API-Key: &lt;key&gt;</code>.
        </p>
        <div className="seg" role="tablist" aria-label="Language">
          {LANGS.map(([id, label]) => <button key={id} role="tab" aria-selected={lang === id} className={lang === id ? "active" : ""} onClick={() => setLang(id)}>{label}</button>)}
        </div>
        <div style={{ marginTop: 10 }}><CodeBlock code={code} label={`${lang} example`} /></div>
        <p className="meta" style={{ margin: "14px 0 8px" }}>The response. This is the real output of the model for the triangle above:</p>
        <CodeBlock code={JSON.stringify(EXAMPLE_RESPONSE, null, 2)} label="Example response" />
        <p className="meta" style={{ marginTop: 10 }}>
          Request body: <code>{JSON.stringify({ strokes: "…", top_k: EXAMPLE_REQUEST.top_k })}</code>, where <code>top_k</code> is 1 to {limits?.top_k_max ?? 10} (default 5).
          Responses carry <code>RateLimit-Limit</code>, <code>RateLimit-Remaining</code> and <code>RateLimit-Reset</code> headers.
        </p>

        <h3 className="sub-h">Limits</h3>
        {limits ? (
          <table aria-label="API limits">
            <tbody>
              <tr><td>Requests per minute, per key</td><td><b>{limits.requests_per_minute}</b></td></tr>
              <tr><td>Requests per day, per key (UTC)</td><td><b>{limits.requests_per_day}</b></td></tr>
              <tr><td>Strokes / points per drawing</td><td><b>{limits.max_strokes}</b> / <b>{limits.max_points}</b></td></tr>
              <tr><td>Active keys per account</td><td><b>{limits.max_active_keys}</b></td></tr>
            </tbody>
          </table>
        ) : <p className="empty">{backend === "offline" ? "Limits are shown when the server is reachable." : "Loading…"}</p>}

        <h3 className="sub-h">Secret keys stay on servers</h3>
        <p className="meta">
          Requests that carry a browser <code>Origin</code> header are refused, so a key that leaks into front-end code cannot be abused from a web page.
          In a web page, use the widget.
        </p>

        <h3 className="sub-h">Errors</h3>
        <p className="meta" style={{ marginBottom: 8 }}>Every error has the shape <code>{`{ "error": { "code": "…", "message": "…" } }`}</code>.</p>
        <table aria-label="Error codes">
          <thead><tr><th>HTTP</th><th>code</th><th>Meaning</th></tr></thead>
          <tbody>{ERRORS.map((e) => <tr key={e.code}><td>{e.status}</td><td><code>{e.code}</code></td><td>{e.meaning}</td></tr>)}</tbody>
        </table>
        <p className="meta" style={{ marginTop: 12 }}>
          {info.data ? <>Model <b>{info.data.version}</b> recognises {info.data.classes.length} objects: {info.data.classes.join(", ")}. The full machine-readable reference is at <a href="/api/docs">/api/docs</a>.</> : null}
        </p>
      </section>

      <KeysManager />
    </div>
  );
}
