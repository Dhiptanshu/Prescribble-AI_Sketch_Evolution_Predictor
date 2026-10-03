import { Link } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import { useEngine } from "../../lib/engine";
import { APP_NAME } from "../../components/Layout";
import { HeroDemo } from "./HeroDemo";

/** Headline numbers come from the model's measured test results (models/<version>/meta.json), never from constants. */
function Stats() {
  const e = useEngine();
  const r = e.status === "ready" ? e.model.meta.test_results : null;
  const pct = (k: string) => (r?.[k] ? `${(r[k]!.top5 * 100).toFixed(1)}%` : "…");
  const items = [
    [pct("0.2"), "Top-5 accuracy with only 20% of the ink"],
    [pct("0.3"), "Top-5 accuracy at 30% of the ink"],
    [pct("1.0"), "Top-5 accuracy on the finished drawing"],
    [e.status === "ready" ? `${e.model.classes.length}` : "…", "object classes recognised today"],
  ] as const;
  return (
    <div className="grid3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
      {items.map(([v, l]) => <div key={l} className="card stat"><b className="gradient-text">{v}</b><span>{l}</span></div>)}
    </div>
  );
}

export function LandingPage() {
  const { user, backend } = useAuth();
  return (
    <>
      <section className="hero">
        <div>
          <h1>The AI that <span className="gradient-text">guesses your drawing</span> before you finish it.</h1>
          <p className="lead">{APP_NAME} reads your strokes as you draw, names what it thinks it is, and paints how it expects the drawing to end.</p>
          <div className="cta">
            <Link className="btn primary lg" to="/studio">Open the Studio</Link>
            {backend === "online" && !user && <Link className="btn lg" to="/register">Create a free account</Link>}
          </div>
          <p className="meta" style={{ marginTop: 14 }}>Runs entirely in your browser. No upload, no camera.</p>
        </div>
        <HeroDemo />
      </section>

      <section className="section">
        <h2>Measured, not promised</h2>
        <p className="sub">Accuracy on held-out QuickDraw sketches the model never saw while training. Live mouse drawings can score lower: the training data came mostly from phones and touch screens.</p>
        <Stats />
      </section>

      <section className="section">
        <h2>How it works</h2>
        <p className="sub">Two views of every drawing, fused: how it looks and the order it was drawn in.</p>
        <div className="grid3">
          <div className="card feature"><h3>Reads strokes, not just pixels</h3><p>A convolutional network sees the shape; an LSTM follows the pen. Together they recognise objects from the first few strokes.</p></div>
          <div className="card feature"><h3>Paints the ending</h3><p>A decoder predicts where the remaining ink will go. When the AI is unsure, the ghost blurs: its uncertainty made visible.</p></div>
          <div className="card feature"><h3>Private by design</h3><p>The model runs on your device in about 20 ms. Your drawings are only stored if you choose to save them.</p></div>
        </div>
      </section>

      <section className="section">
        <h2>What is next</h2>
        <p className="sub">Live now: the daily challenge, with a new word every day and a leaderboard, and a developer platform (an embeddable widget and a REST API). On the roadmap, not live yet: classroom rooms.</p>
      </section>
    </>
  );
}
