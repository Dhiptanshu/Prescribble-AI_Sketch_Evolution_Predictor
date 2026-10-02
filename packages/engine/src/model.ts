// ONNX Runtime Web wrapper. Runs entirely in the browser (WASM, single thread: no special server headers needed).
import * as ort from "onnxruntime-web/wasm";
import { IMG, MAX_PTS, SEQ_FEATS, rasterize, simplify, toSeq, type Stroke } from "./pipeline";

export interface FractionResult { top1: number; top5: number }
export interface ModelMeta {
  model: string;
  version?: string;
  classes: string[];
  test_results: Record<string, FractionResult>;
  latency_ms: number;
  size_mb: number;
}

export interface Guess { idx: number; name: string; p: number }
export interface Prediction {
  probs: Float32Array;
  top5: Guess[];
  /** Expected full drawing (IMG*IMG, 0..1) as predicted by the ghost decoder. */
  ghost: Float32Array;
  /** The partial raster that was fed to the network. */
  img: Float32Array;
  /** Normalised entropy of the class distribution (0 = certain, 1 = uniform). */
  entropy: number;
  ms: number;
}

export interface LoadOptions {
  /** Folder containing sketch.onnx and meta.json, with trailing slash. */
  modelBase: string;
  /** Folder containing ort-wasm-simd-threaded.{mjs,wasm}, with trailing slash. */
  wasmBase: string;
}

const abs = (p: string) => new URL(p, typeof document !== "undefined" ? document.baseURI : location.href).href;

export class SketchModel {
  private constructor(private session: ort.InferenceSession, readonly meta: ModelMeta) {}

  static async load({ modelBase, wasmBase }: LoadOptions): Promise<SketchModel> {
    ort.env.wasm.wasmPaths = abs(wasmBase);   // must be absolute for the module loader
    ort.env.wasm.numThreads = 1;
    const meta = (await (await fetch(modelBase + "meta.json")).json()) as ModelMeta;
    const session = await ort.InferenceSession.create(modelBase + "sketch.onnx", { executionProviders: ["wasm"] });
    return new SketchModel(session, meta);
  }

  get classes(): string[] {
    return this.meta.classes;
  }

  /** Predict from raw strokes in the 0..255 frame. Returns null when there is nothing drawn. */
  async predict(raw: Stroke[]): Promise<Prediction | null> {
    const strokes = simplify(raw);
    if (!strokes.length) return null;
    const img = rasterize(strokes);
    const { seq, length } = toSeq(strokes);
    const t0 = performance.now();
    const out = await this.session.run({
      img: new ort.Tensor("float32", img, [1, 1, IMG, IMG]),
      seq: new ort.Tensor("float32", seq, [1, MAX_PTS, SEQ_FEATS]),
      length: new ort.Tensor("int64", BigInt64Array.from([BigInt(length)]), [1]),
    });
    const ms = performance.now() - t0;
    const probs = out.probs!.data as Float32Array;
    const order = Array.from(probs, (_, i) => i).sort((a, b) => probs[b]! - probs[a]!);
    let h = 0;
    for (const p of probs) if (p > 1e-9) h -= p * Math.log(p);
    return {
      probs,
      top5: order.slice(0, 5).map((idx) => ({ idx, name: this.classes[idx]!, p: probs[idx]! })),
      ghost: out.ghost!.data as Float32Array,
      img,
      entropy: h / Math.log(probs.length),
      ms,
    };
  }
}
