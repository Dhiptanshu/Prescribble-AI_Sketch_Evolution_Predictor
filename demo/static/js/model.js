// Thin wrapper around ONNX Runtime Web (WASM, single thread so no special server headers are needed).
import { IMG, MAX_PTS, SEQ_FEATS, rasterize, simplify, toSeq } from "./pipeline.js";

export class SketchModel {
  async load(base = "models/") {
    const ort = window.ort;
    ort.env.wasm.wasmPaths = new URL("vendor/ort/", document.baseURI).href;   // must be absolute for the module loader
    ort.env.wasm.numThreads = 1;
    this.ort = ort;
    this.meta = await (await fetch(base + "meta.json")).json();
    this.classes = this.meta.classes;
    this.session = await ort.InferenceSession.create(base + "sketch.onnx", { executionProviders: ["wasm"] });
    return this;
  }

  // strokes: [[ [x,y],... ], ...] in the 0..255 frame. Returns real model outputs + measured latency.
  async predict(rawStrokes) {
    const strokes = simplify(rawStrokes);
    if (!strokes.length) return null;
    const ort = this.ort;
    const img = rasterize(strokes);
    const { seq, length } = toSeq(strokes);
    const t0 = performance.now();
    const out = await this.session.run({
      img: new ort.Tensor("float32", img, [1, 1, IMG, IMG]),
      seq: new ort.Tensor("float32", seq, [1, MAX_PTS, SEQ_FEATS]),
      length: new ort.Tensor("int64", BigInt64Array.from([BigInt(length)]), [1]),
    });
    const ms = performance.now() - t0;
    const probs = Array.from(out.probs.data);
    const order = probs.map((p, i) => i).sort((a, b) => probs[b] - probs[a]);
    const entropy = -probs.reduce((s, p) => s + (p > 1e-9 ? p * Math.log(p) : 0), 0) / Math.log(probs.length);
    return { probs, top5: order.slice(0, 5).map((i) => ({ idx: i, name: this.classes[i], p: probs[i] })), ghost: out.ghost.data, img, entropy, ms };
  }
}
