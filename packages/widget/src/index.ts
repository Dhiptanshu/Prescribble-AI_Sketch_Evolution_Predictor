// Entry point of the embeddable widget. Loaded with a plain <script> tag; exposes window.Prescribble and <prescribble-canvas>.
import { mount, scriptSource, type MountOptions, type WidgetHandle } from "./widget";
import { clampSize, type ThemeOption } from "./util";

// document.currentScript is only available while the script is being evaluated, so capture where it came from right away.
scriptSource.src = document.currentScript instanceof HTMLScriptElement ? document.currentScript.src : null;

export const version = "0.1.0";
export { mount };
export type { MountOptions, WidgetHandle };

/**
 * <prescribble-canvas size="360" theme="auto" no-guesses></prescribble-canvas>
 * Fires a `guess` event ({ detail: { top5, ink, strokes } }) and exposes clear(), undo() and getStrokes().
 */
class PrescribbleCanvas extends HTMLElement {
  private handle: WidgetHandle | null = null;

  connectedCallback() {
    if (this.handle) return;
    const theme = this.getAttribute("theme");
    this.handle = mount(this, {
      size: clampSize(this.getAttribute("size")),
      theme: theme === "light" || theme === "dark" || theme === "auto" ? (theme as ThemeOption) : "auto",
      showGuesses: !this.hasAttribute("no-guesses"),
      assetsBase: this.getAttribute("assets-base") ?? undefined,
      onGuess: (detail) => this.dispatchEvent(new CustomEvent("guess", { detail, bubbles: true, composed: true })),
      onReady: (detail) => this.dispatchEvent(new CustomEvent("ready", { detail, bubbles: true, composed: true })),
      onError: (error) => this.dispatchEvent(new CustomEvent("error", { detail: error, bubbles: true, composed: true })),
    });
  }

  disconnectedCallback() {
    this.handle?.destroy();
    this.handle = null;
  }

  clear() { this.handle?.clear(); }
  undo() { this.handle?.undo(); }
  getStrokes() { return this.handle?.getStrokes() ?? []; }
}

if (!customElements.get("prescribble-canvas")) customElements.define("prescribble-canvas", PrescribbleCanvas);

// Global for classic <script> use: window.Prescribble.mount("#el", { ... })
(window as unknown as { Prescribble: unknown }).Prescribble = { mount, version };
