import { useEffect, useRef, useState } from "react";
import { formatClock, remaining } from "../../lib/rooms";

/** Counts down from the seconds the server reported at `receivedAt`. Calls `onZero` once when it runs out. */
export function RoundClock({ seconds, receivedAt, onZero }: { seconds: number; receivedAt: number; onZero?: () => void }) {
  const [left, setLeft] = useState(() => remaining(seconds, receivedAt, Date.now()));
  const fired = useRef(false);
  const zero = useRef(onZero);
  zero.current = onZero;

  useEffect(() => {
    fired.current = false;
    const tick = () => {
      const r = remaining(seconds, receivedAt, Date.now());
      setLeft(r);
      if (r <= 0 && !fired.current) { fired.current = true; zero.current?.(); }
    };
    tick();
    const t = setInterval(tick, 250);
    return () => clearInterval(t);
  }, [seconds, receivedAt]);

  return <span className="round-clock" role="timer" aria-label="Time left in the round">{formatClock(left)}</span>;
}
