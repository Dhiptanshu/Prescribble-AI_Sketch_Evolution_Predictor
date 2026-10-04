// Runs the whole product on one port for hands-on testing: the API serving the BUILT web app (single-origin mode) with a persistent local database.
//   npm run build:web && node scripts/run_local.mjs        then open http://localhost:8100
// The database file is apps/api/prescribble.db (git-ignored): accounts, drawings and rooms survive restarts. Delete it to start fresh.
import { spawn } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repo = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const api = join(repo, "apps", "api");
const python = process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3");

const child = spawn(python, ["-m", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1", "--port", "8100"], {
  cwd: api,
  stdio: "inherit",
  env: {
    ...process.env,
    PRESCRIBBLE_ENV: "dev",
    PRESCRIBBLE_DATABASE_URL: `sqlite:///${join(api, "prescribble.db").replaceAll("\\", "/")}`,
    PRESCRIBBLE_WEB_DIST: join(repo, "apps", "web", "dist"),
  },
});
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => child.kill());
child.on("exit", (code) => process.exit(code ?? 0));
