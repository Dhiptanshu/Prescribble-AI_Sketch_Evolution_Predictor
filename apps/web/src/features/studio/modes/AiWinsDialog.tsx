import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

interface Props {
  target: string;
  strokes: number;
  /** The AI's confidence in the target at the moment it won, 0..1. */
  confidence: number;
  onNext: () => void;
  onClose: () => void;
}

/** Shown when the AI names the target before the player is done. The pen was stopped at the drawing the AI saw, so the race is fair. */
export function AiWinsDialog({ target, strokes, confidence, onNext, onClose }: Props) {
  const next = useRef<HTMLButtonElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;                                  // the parent passes a new function every render; the effect below must not re-run (it would pull focus back)
  useEffect(() => {
    next.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close.current(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Rendered on <body>: the cards have a backdrop blur, which makes a position:fixed child position itself inside the card instead of on the screen.
  return createPortal(
    // A player who is still pressing the pen must not dismiss the popup by accident: only the buttons and Escape close it, and a press on the backdrop keeps the focus where it is.
    <div className="modal-backdrop" onMouseDown={(e) => e.preventDefault()}>
      <div ref={box} className="modal card" role="dialog" aria-modal="true" aria-labelledby="ai-wins-title" aria-describedby="ai-wins-text"
        onBlur={(e) => { if (!e.relatedTarget) queueMicrotask(() => next.current?.focus()); }}      // focus fell to the page (a press on the canvas below): bring it back into the dialog
        onKeyDown={(e) => {                                                                          // Tab cycles inside the dialog
          if (e.key !== "Tab") return;
          const items = Array.from(box.current?.querySelectorAll<HTMLElement>("button") ?? []);
          const at = items.indexOf(document.activeElement as HTMLElement), step = e.shiftKey ? -1 : 1;
          e.preventDefault();
          items[(at + step + items.length) % items.length]?.focus();
        }}>
        <h2 id="ai-wins-title" className="modal-title gradient-text">AI wins!</h2>
        <p id="ai-wins-text">
          It recognised your <b>{target}</b> after {strokes} stroke{strokes === 1 ? "" : "s"}, {Math.round(confidence * 100)}% sure.
        </p>
        <p className="meta">Your pen was stopped at the drawing the AI had seen, so the race stays fair.</p>
        <div className="modal-actions">
          <button ref={next} className="btn primary" onClick={onNext}>Next word</button>
          <button className="btn" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  , document.body);
}
