// Starts the real API (fresh temp database) serving the BUILT web app on :8110, exactly as a single-container deploy would.
import { spawn } from "node:child_process";
import { rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const db = join(tmpdir(), "prescribble-e2e.db").replaceAll("\\", "/");
rmSync(db, { force: true });

const python = process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3");
const child = spawn(python, ["-m", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1", "--port", "8110"], {
  cwd: resolve(web, "../api"),
  stdio: "inherit",
  env: {
    ...process.env,
    PRESCRIBBLE_ENV: "dev",
    PRESCRIBBLE_DATABASE_URL: `sqlite:///${db}`,
    PRESCRIBBLE_WEB_DIST: resolve(web, "dist"),
    PRESCRIBBLE_AUTH_ATTEMPTS_PER_MINUTE: "1000",   // tests register and log in many times from one IP
  },
});
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => child.kill());
child.on("exit", (code) => process.exit(code ?? 0));
