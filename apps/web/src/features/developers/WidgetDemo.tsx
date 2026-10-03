import { useEffect, useRef, useState } from "react";

interface Guess { label: string; probability: number }
interface Handle { destroy(): void; clear(): void }
type PrescribbleGlobal = { mount(target: Element, options: Record<string, unknown>): Handle };

function loadWidgetScript(): Promise<PrescribbleGlobal> {
  const w = window as unknown as { Prescribble?: PrescribbleGlobal };
  if (w.Prescribble) return Promise.resolve(w.Prescribble);
  return new Promise((resolve, reject) => {
    const s = Object.assign(document.createElement("script"), { src: `${import.meta.env.BASE_URL}widget/prescribble-widget.js`, async: true });
    s.onload = () => (w.Prescribble ? resolve(w.Prescribble) : reject(new Error("widget did not initialise")));
    s.onerror = () => reject(new Error("could not load the widget script"));
    document.head.append(s);
  });
}

/** The real embeddable widget, loaded exactly the way a customer's page would load it. The panel shows the events your code receives. */
export function WidgetDemo() {
  const host = useRef<HTMLDivElement>(null);
  const [last, setLast] = useState<{ top5: Guess[]; ink: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let handle: Handle | null = null, node: HTMLDivElement | null = null, alive = true;
    loadWidgetScript().then((P) => {
      if (!alive || !host.current) return;
      node = document.createElement("div");           // a fresh element per mount: shadow roots can only be attached once
      host.current.append(node);
      handle = P.mount(node, { size: 320, onGuess: (e: { top5: Guess[]; ink: number }) => setLast({ top5: e.top5, ink: e.ink }), onError: (e: Error) => setError(e.message) });
    }).catch((e: Error) => setError(e.message));
    return () => { alive = false; handle?.destroy(); node?.remove(); };
  }, []);

  return (
    <div className="widget-demo">
      <div ref={host} aria-label="Live widget demo" />
      <div>
        <div className="meta" style={{ marginBottom: 6 }}>What <code>onGuess</code> receives</div>
        <pre className="code" aria-label="Last guess event">{error ? `error: ${error}` : last ? JSON.stringify({ top5: last.top5.slice(0, 3), ink: last.ink }, null, 2) : "// draw in the box to see the event"}</pre>
      </div>
    </div>
  );
}
