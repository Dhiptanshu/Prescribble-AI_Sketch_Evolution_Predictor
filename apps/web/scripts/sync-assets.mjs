// Copies runtime assets into public/ before dev/build:
//  - ONNX Runtime Web WASM files   (from node_modules, so versions always match the installed package)
//  - the versioned model artefacts (from /models/<version>, the single source of truth)
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
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

const models = join(repo, "models");
if (!existsSync(join(models, "v1/sketch.onnx"))) throw new Error("models/v1/sketch.onnx is missing");
rmSync(join(pub, "models"), { recursive: true, force: true });
cpSync(models, join(pub, "models"), { recursive: true });
console.log("assets synced: ort wasm + models/");
