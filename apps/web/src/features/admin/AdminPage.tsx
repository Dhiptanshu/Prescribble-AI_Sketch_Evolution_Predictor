import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { drawBarChart } from "../../components/charts";
import { RequireAuth } from "../../components/RequireAuth";
import { useAuth } from "../../lib/auth";
import { useAdminMetrics } from "../../lib/platform";

function Tile({ value, label, hint }: { value: string; label: string; hint?: string }) {
  return (
    <div className="card stat">
      <b className="gradient-text">{value}</b>
      <span>{label}</span>
      {hint && <span className="meta">{hint}</span>}
    </div>
  );
}

function Dashboard() {
  const q = useAdminMetrics();
  const ref = useRef<HTMLCanvasElement>(null);
  const daily = q.data?.api.daily;
  useEffect(() => {
    const c = ref.current;
    if (!c || !daily) return;
    const bars = daily.map((d) => ({ label: d.day.slice(5), value: d.requests }));
    const paint = () => drawBarChart(c, bars);
    paint();
    const ro = new ResizeObserver(paint);
    ro.observe(c);
    const mo = new MutationObserver(paint);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => { ro.disconnect(); mo.disconnect(); };
  }, [daily]);

  if (q.isLoading) return <p className="empty">Loading…</p>;
  if (!q.data) return <p className="empty">Could not load the metrics.</p>;
  const m = q.data;
  const errRate = m.api.requests_7d ? `${((m.api.errors_7d / m.api.requests_7d) * 100).toFixed(1)}% error rate` : "no traffic yet";

  return (
    <section aria-label="Admin dashboard">
      <div className="page-head"><h1>Operations</h1><span className="meta">model {m.model_version} · {m.model_loaded ? "loaded" : "idle (loads on first use)"}</span></div>
      <div className="tiles">
        <Tile value={String(m.users.total)} label="accounts" hint={`${m.users.last_7_days} in the last 7 days`} />
        <Tile value={String(m.drawings.total)} label="saved drawings" hint={`${m.drawings.last_7_days} in the last 7 days`} />
        <Tile value={String(m.challenge_today.players)} label="challenge players today" hint={`${m.challenge_today.attempts} attempts, ${m.challenge_today.flagged} flagged`} />
        <Tile value={String(m.api.active_keys)} label="active API keys" hint={`${m.api.requests_today} requests today`} />
      </div>
      <div className="stats-grid">
        <section className="card">
          <div className="card-head"><h2>API requests per day</h2><span className="meta">last 14 days</span></div>
          <canvas ref={ref} className="chart" role="img" aria-label="API requests per day" />
          <p className="meta">Last 7 days: {m.api.requests_7d} requests · {errRate}{m.api.avg_ms_7d != null ? ` · ${m.api.avg_ms_7d} ms average model time` : ""}</p>
        </section>
        <section className="card">
          <div className="card-head"><h2>Busiest keys</h2><span className="meta">last 7 days</span></div>
          {m.api.top_keys.length ? (
            <table aria-label="Busiest API keys">
              <thead><tr><th>Key</th><th>Owner</th><th>Requests</th></tr></thead>
              <tbody>{m.api.top_keys.map((k) => <tr key={k.prefix}><td><code>{k.prefix}…</code> {k.name}</td><td>{k.owner}</td><td>{k.requests_7d}</td></tr>)}</tbody>
            </table>
          ) : <p className="empty">No API traffic yet.</p>}
        </section>
      </div>
    </section>
  );
}

/** Operator dashboard. Admins are promoted on the server (python -m app.cli make-admin <email>), never from this site. */
export function AdminPage() {
  return (
    <RequireAuth>
      <AdminGate />
    </RequireAuth>
  );
}

function AdminGate() {
  const { user } = useAuth();
  if (!user?.is_admin) {
    return (
      <div className="auth-wrap card">
        <h1>Admins only</h1>
        <p className="sub">This page is for operators of this server.</p>
        <Link className="btn primary" to="/studio">Back to the Studio</Link>
      </div>
    );
  }
  return <Dashboard />;
}
