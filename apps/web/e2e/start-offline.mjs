// Starts the stdlib static server (no backend) on :8111: the same script the lab bundle ships.
import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const python = process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3");
const child = spawn(python, ["serve.py", "8111"], { cwd: web, stdio: "inherit" });
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => child.kill());
child.on("exit", (code) => process.exit(code ?? 0));
