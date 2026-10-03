import { Link } from "react-router-dom";
import { StrokeThumb } from "../../components/StrokeThumb";
import { formatDate, recognitionText } from "../../lib/format";
import { useDrawings } from "../../lib/drawings";

export function GalleryPage() {
  const q = useDrawings();
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <section aria-label="Your gallery">
      <div className="page-head">
        <h1>Your gallery</h1>
        <Link className="btn primary" to="/studio">New drawing</Link>
      </div>
      {q.isLoading && <p className="empty">Loading…</p>}
      {q.isError && <p className="empty">Could not load your drawings. Try again in a moment.</p>}
      {q.isSuccess && !items.length && (
        <div className="card empty-state">
          <h2>No drawings yet</h2>
          <p>Draw something in the Studio and press <b>Save drawing</b>. It will appear here, ready to replay, share or export as a video.</p>
          <Link className="btn primary" to="/studio">Open the Studio</Link>
        </div>
      )}
      <div className="gallery">
        {items.map((d) => (
          <Link key={d.id} to={`/gallery/${d.id}`} className="card tile" aria-label={`${d.label ?? "Unlabelled"} drawing from ${formatDate(d.created_at)}`}>
            <StrokeThumb strokes={d.strokes} label={`Drawing of ${d.label ?? "something"}`} />
            <div className="tile-body">
              <b>{d.label ?? "Unlabelled"}</b>
              {d.share_token && <span className="chip" title="Anyone with the link can view it">shared</span>}
            </div>
            <span className="meta">{recognitionText(d.label, d.recognised_at, d.ai_guess)}</span>
            <span className="meta">{formatDate(d.created_at)} · {d.n_strokes} stroke{d.n_strokes === 1 ? "" : "s"}</span>
          </Link>
        ))}
      </div>
      {q.hasNextPage && (
        <div style={{ textAlign: "center", marginTop: 20 }}>
          <button className="btn" onClick={() => void q.fetchNextPage()} disabled={q.isFetchingNextPage}>{q.isFetchingNextPage ? "Loading…" : "Load more"}</button>
        </div>
      )}
    </section>
  );
}
