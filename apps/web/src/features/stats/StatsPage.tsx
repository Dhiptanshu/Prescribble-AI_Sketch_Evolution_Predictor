import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { drawBarChart } from "../../components/charts";
import { useStats, type Stats } from "../../lib/drawings";
import { formatDate, percent } from "../../lib/format";

function ActivityChart({ activity }: { activity: Stats["activity"] }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current!;
    const bars = activity.map((a) => ({ label: a.date.slice(5), value: a.count }));
    const paint = () => drawBarChart(c, bars);
    paint();
    const ro = new ResizeObserver(paint);
    ro.observe(c);
    const mo = new MutationObserver(paint);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => { ro.disconnect(); mo.disconnect(); };
  }, [activity]);
  return <canvas ref={ref} className="chart" role="img" aria-label="Drawings saved per day, last 30 days" />;
}

function Tile({ value, label, hint }: { value: string; label: string; hint?: string }) {
  return (
    <div className="card stat">
      <b className="gradient-text">{value}</b>
      <span>{label}</span>
      {hint && <span className="meta">{hint}</span>}
    </div>
  );
}

/** Everything here is computed by the server from the signed-in user's own saved drawings. */
export function StatsPage() {
  const q = useStats();
  if (q.isLoading) return <p className="empty">Loading…</p>;
  if (q.isError || !q.data) return <p className="empty">Could not load your stats. Try again in a moment.</p>;
  const s = q.data;

  if (!s.total) {
    return (
      <div className="card empty-state">
        <h2>No stats yet</h2>
        <p>Your numbers appear here once you save drawings: how early the AI recognises them, your streak and your most-drawn objects.</p>
        <Link className="btn primary" to="/studio">Open the Studio</Link>
      </div>
    );
  }
  return (
    <section aria-label="Your stats">
      <div className="page-head"><h1>Your stats</h1><span className="meta">since {s.first_drawing_at ? formatDate(s.first_drawing_at) : "—"}</span></div>
      <div className="tiles">
        <Tile value={String(s.total)} label="drawings saved" hint={`${s.labelled} labelled`} />
        <Tile value={s.early_rate != null ? percent(s.early_rate) : "—"} label="recognised by 30% of the ink" hint={s.labelled ? `of ${s.labelled} labelled drawings` : "label a drawing to see this"} />
        <Tile value={s.avg_recognised_at != null ? percent(s.avg_recognised_at) : "—"} label="average recognition point" hint="of the ink, when the AI got it" />
        <Tile value={`${s.streak.current} day${s.streak.current === 1 ? "" : "s"}`} label="current streak" hint={`longest ${s.streak.longest}`} />
      </div>

      <div className="stats-grid">
        <section className="card">
          <div className="card-head"><h2>Drawings per day</h2><span className="meta">last 30 days</span></div>
          <ActivityChart activity={s.activity} />
        </section>
        <section className="card">
          <div className="card-head"><h2>By object</h2><span className="meta">{s.by_class.length} different</span></div>
          {s.by_class.length ? (
            <table>
              <thead><tr><th>Object</th><th>Drawings</th><th>AI had it by</th></tr></thead>
              <tbody>
                {s.by_class.map((c) => (
                  <tr key={c.label}><td>{c.label}</td><td>{c.count}</td><td>{c.avg_recognised_at != null ? percent(c.avg_recognised_at) : "—"}</td></tr>
                ))}
              </tbody>
            </table>
          ) : <p className="empty">Label your drawings to see them here.</p>}
          <p className="meta" style={{ marginTop: 10 }}>“AI had it by” is the average share of the ink after which the AI’s first guess was the right one. Lower is better.</p>
        </section>
      </div>
    </section>
  );
}
