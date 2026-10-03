// Copies runtime assets into public/ before dev/build:
//  - ONNX Runtime Web WASM files   (from node_modules, so versions always match the installed package)
//  - the versioned model artefacts (from /models/<version>, the single source of truth)
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const web = resolve(here, "..");
const repo = resolve(web, "../..");
const pub = join(web, "public");

const ortDist = [join(repo, "node_modules/onnxruntime-web/dist"), join(web, "node_modules/onnxruntime-web/dist")].find(existsSync);
if (!ortDist) throw new Error("onnxruntime-web not installed. Run `npm install` at the repo root.");

rmSync(join(pub, "ort"), { recursive: true, force: true });
mkdirSync(join(pub, "ort"), { recursive: true });
for (const f of ["ort-wasm-simd-threaded.mjs", "ort-wasm-simd-threaded.wasm"]) cpSync(join(ortDist, f), join(pub, "ort", f));

// Only the live version ships with the web build (and the registry that names it): older and candidate versions stay in the repo, not in every
// copy of the app, so the lab bundle does not grow with every model generation. Set SHIP_ALL_MODELS=1 to copy them all.
const models = join(repo, "models");
const registryFile = join(models, "registry.json");
const active = existsSync(registryFile) ? JSON.parse(readFileSync(registryFile, "utf-8")).active ?? "v1" : "v1";
if (!existsSync(join(models, active, "sketch.onnx"))) throw new Error(`models/${active}/sketch.onnx is missing (the live version in models/registry.json)`);
rmSync(join(pub, "models"), { recursive: true, force: true });
mkdirSync(join(pub, "models"), { recursive: true });
if (existsSync(registryFile)) cpSync(registryFile, join(pub, "models", "registry.json"));
for (const version of process.env.SHIP_ALL_MODELS ? readdirSync(models).filter((d) => existsSync(join(models, d, "sketch.onnx"))) : [active]) {
  cpSync(join(models, version), join(pub, "models", version), { recursive: true });
}
// The embeddable widget (built by `npm run build:widget`) is served from /widget/ for other websites to <script src> it.
const widget = join(repo, "packages/widget/dist/prescribble-widget.js");
if (!existsSync(widget)) throw new Error("widget not built. Run `npm run build:widget` (or `npm run build:web`, which does it first).");
rmSync(join(pub, "widget"), { recursive: true, force: true });
mkdirSync(join(pub, "widget"), { recursive: true });
cpSync(widget, join(pub, "widget/prescribble-widget.js"));
console.log("assets synced: ort wasm + models/ + widget/");
