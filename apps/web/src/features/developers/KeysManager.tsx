import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { drawBarChart } from "../../components/charts";
import { CodeBlock } from "../../components/CodeBlock";
import { ApiError } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { formatDate } from "../../lib/format";
import { useKeyActions, useKeys, useKeyUsage, type CreatedKey } from "../../lib/platform";

function UsageChart({ id }: { id: number }) {
  const q = useKeyUsage(id);
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c || !q.data) return;
    const bars = q.data.map((d) => ({ label: d.day.slice(5), value: d.requests }));
    const paint = () => drawBarChart(c, bars);
    paint();
    const ro = new ResizeObserver(paint);
    ro.observe(c);
    const mo = new MutationObserver(paint);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => { ro.disconnect(); mo.disconnect(); };
  }, [q.data]);
  if (q.isLoading) return <p className="empty">Loading usage…</p>;
  if (!q.data) return <p className="empty">Could not load usage.</p>;
  const total = q.data.reduce((a, d) => a + d.requests, 0), errors = q.data.reduce((a, d) => a + d.errors, 0);
  const timed = q.data.filter((d) => d.avg_ms != null && d.requests);
  const avg = timed.length ? timed.reduce((a, d) => a + (d.avg_ms ?? 0) * d.requests, 0) / timed.reduce((a, d) => a + d.requests, 0) : null;
  return (
    <>
      <canvas ref={ref} className="chart" role="img" aria-label="Requests per day, last 14 days" />
      <p className="meta">Last 14 days: {total} request{total === 1 ? "" : "s"}, {errors} error{errors === 1 ? "" : "s"}{avg != null ? `, ${avg.toFixed(1)} ms average` : ""}</p>
    </>
  );
}

/** Create, view and revoke API keys. The full key is shown once, right after it is created, and never again. */
export function KeysManager() {
  const { user, backend } = useAuth();
  const keys = useKeys(!!user);
  const { create, revoke } = useKeyActions();
  const [name, setName] = useState("");
  const [fresh, setFresh] = useState<CreatedKey | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [confirming, setConfirming] = useState<number | null>(null);

  if (backend !== "online") return null;
  if (!user) {
    return (
      <section className="card" aria-label="API keys">
        <div className="card-head"><h2>Your API keys</h2></div>
        <p className="meta" style={{ marginBottom: 12 }}>Sign in to create a key for the REST API. The widget needs no key.</p>
        <div style={{ display: "flex", gap: 8 }}>
          <Link className="btn primary" to="/login" state={{ from: "/developers" }}>Sign in</Link>
          <Link className="btn" to="/register" state={{ from: "/developers" }}>Create account</Link>
        </div>
      </section>
    );
  }

  const onCreate = (e: FormEvent) => {
    e.preventDefault();
    create.mutate(name, { onSuccess: (k) => { setFresh(k); setName(""); setSelected(k.id); } });
  };
  const createError = create.error instanceof ApiError ? create.error.message : create.error ? "Could not reach the server." : null;
  const list = keys.data ?? [];

  return (
    <section className="card" aria-label="API keys">
      <div className="card-head"><h2>Your API keys</h2><span className="meta">{list.filter((k) => !k.revoked_at).length} active</span></div>

      {fresh && (
        <div className="toast good new-key" role="status">
          <b>Copy your new key now.</b> For your security it is shown only once and we store just a fingerprint.
          <CodeBlock code={fresh.key} label="New API key" />
          <button className="btn" onClick={() => setFresh(null)}>I have saved it</button>
        </div>
      )}

      <form className="form key-form" onSubmit={onCreate}>
        <div className="field">
          <label htmlFor="key-name">Name for a new key</label>
          <input id="key-name" className="input" maxLength={60} placeholder="e.g. production backend" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <button className="btn primary" disabled={!name.trim() || create.isPending}>{create.isPending ? "Creating…" : "Create key"}</button>
      </form>
      {createError && <div className="toast bad" role="alert" style={{ marginTop: 10 }}>{createError}</div>}

      {keys.isLoading && <p className="empty">Loading…</p>}
      {keys.isSuccess && !list.length && <p className="empty">No keys yet. Create one to call the REST API from your server.</p>}
      {!!list.length && (
        <table aria-label="Your API keys" style={{ marginTop: 14 }}>
          <thead><tr><th>Name</th><th>Key</th><th>Today</th><th>Last used</th><th /></tr></thead>
          <tbody>
            {list.map((k) => (
              <tr key={k.id} className={k.revoked_at ? "revoked" : undefined}>
                <td>{k.name}{k.revoked_at && <span className="pill"> revoked</span>}</td>
                <td><code>{k.prefix}…</code></td>
                <td>{k.used_today} / {k.daily_limit}</td>
                <td>{k.last_used_at ? formatDate(k.last_used_at) : "never"}</td>
                <td className="actions">
                  <button className="btn ghost" onClick={() => setSelected(selected === k.id ? null : k.id)} aria-label={`Usage for ${k.name}`}>{selected === k.id ? "Hide usage" : "Usage"}</button>
                  {!k.revoked_at && (confirming === k.id ? (
                    <>
                      <button className="btn" style={{ borderColor: "var(--bad)" }} disabled={revoke.isPending} onClick={() => revoke.mutate(k.id, { onSuccess: () => setConfirming(null) })}>Revoke now</button>
                      <button className="btn ghost" onClick={() => setConfirming(null)}>Cancel</button>
                    </>
                  ) : <button className="btn ghost" onClick={() => setConfirming(k.id)} aria-label={`Revoke ${k.name}`}>Revoke</button>)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {selected !== null && <div style={{ marginTop: 16 }}><UsageChart id={selected} /></div>}
    </section>
  );
}
