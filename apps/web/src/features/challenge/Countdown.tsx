import { useEffect, useState } from "react";
import { formatCountdown } from "../../lib/challenge";

/** Ticks down to the next UTC midnight. Calls `onDone` once when it reaches zero so the page can fetch the new word. */
export function Countdown({ seconds, onDone }: { seconds: number; onDone: () => void }) {
  const [left, setLeft] = useState(seconds);
  useEffect(() => setLeft(seconds), [seconds]);
  useEffect(() => {
    const t = setInterval(() => setLeft((l) => l - 1), 1000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => { if (left === 0) onDone(); }, [left, onDone]);
  return <span className="meta" aria-label="Time until the next word">{formatCountdown(left)}</span>;
}
