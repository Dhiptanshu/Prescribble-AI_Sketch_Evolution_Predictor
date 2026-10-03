import { useState } from "react";

/** A code sample with a copy button. */
export function CodeBlock({ code, label }: { code: string; label: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try { await navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 1800); } catch { /* clipboard blocked: the text is selectable */ }
  }
  return (
    <div className="codewrap">
      <button className="btn copy" onClick={() => void copy()} aria-label={`Copy ${label}`}>{copied ? "Copied" : "Copy"}</button>
      <pre className="code" tabIndex={0} aria-label={label}><code>{code}</code></pre>
    </div>
  );
}
