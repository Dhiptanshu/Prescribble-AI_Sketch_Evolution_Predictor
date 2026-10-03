import { execFileSync } from "node:child_process";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { expect, test, type Page, type Request } from "@playwright/test";
import { HOUSE, watchErrors } from "./helpers";

const PASSWORD = "Phase-Four-Passphrase-52";
const API_ORIGIN = "http://127.0.0.1:8110";
const TRIANGLE = [[[20, 200], [128, 40], [236, 200], [20, 200]]];

async function signUp(page: Page, name: string) {
  const email = `p4.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Display name").fill(name);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel(/Password/).fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/studio$/);
  return email;
}

/** Promote an account the only way it can be done: the operator CLI on the server (never through the public API). */
function makeAdmin(email: string) {
  execFileSync(process.platform === "win32" ? "python" : "python3", ["-m", "app.cli", "make-admin", email], {
    cwd: resolve(process.cwd(), "../api"),
    env: { ...process.env, PRESCRIBBLE_DATABASE_URL: `sqlite:///${join(tmpdir(), "prescribble-e2e.db").replaceAll("\\", "/")}` },
    stdio: "pipe",
  });
}

test.describe("phase 4: developer platform", () => {
  test("the public docs show real examples and live limits", async ({ page, request }) => {
    const errors = watchErrors(page);
    const info = await (await request.get("/api/v1/model")).json();
    await page.goto("/developers");
    await expect(page.getByRole("heading", { name: "Build with Prescribble" })).toBeVisible();

    // numbers come from the server's settings, not from the page
    const limits = page.getByRole("table", { name: "API limits" });
    await expect(limits).toContainText(String(info.limits.requests_per_minute));
    await expect(limits).toContainText(String(info.limits.requests_per_day));

    // the example response is the model's real output for the documented request
    await expect(page.getByLabel("Example response", { exact: true })).toContainText('"label": "pizza"');
    await expect(page.getByLabel("curl example", { exact: true })).toContainText("Authorization: Bearer $PRESCRIBBLE_KEY");
    await page.getByRole("tab", { name: "Python" }).click();
    await expect(page.getByLabel("python example", { exact: true })).toContainText("requests.post");
    await expect(page.getByRole("table", { name: "Error codes" })).toContainText("quota_exceeded");
    await expect(page.getByText(`recognises ${info.classes.length} objects`)).toBeVisible();

    // not signed in: the keys area invites sign-in instead of failing
    await expect(page.getByRole("region", { name: "API keys" }).getByRole("link", { name: "Sign in" })).toBeVisible();
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("the live widget on the docs page emits real guesses", async ({ page }) => {
    await page.goto("/developers");
    const demo = page.getByLabel("Live widget demo");
    await expect(demo.locator("canvas.draw")).toBeVisible({ timeout: 30_000 });
    await expect(demo.getByText("Draw anything. The AI guesses as you go.")).toBeVisible({ timeout: 40_000 });
    const box = (await demo.locator("canvas.draw").boundingBox())!;
    const at = ([x, y]: number[]) => ({ x: box.x + (x! / 255) * box.width, y: box.y + (y! / 255) * box.height });
    for (const s of HOUSE) {
      const first = at(s[0]!);
      await page.mouse.move(first.x, first.y);
      await page.mouse.down();
      for (const p of s.slice(1)) { const q = at(p); await page.mouse.move(q.x, q.y, { steps: 6 }); }
      await page.mouse.up();
    }
    await expect(page.getByLabel("Last guess event", { exact: true })).toContainText('"label": "house"', { timeout: 15_000 });
    await expect(demo.locator(".top")).toContainText("house");
  });

  test("API keys: create, use from a server, meter, refuse browsers, revoke", async ({ page, request }) => {
    const errors = watchErrors(page);
    await signUp(page, "Dana Dev");
    await page.goto("/developers");
    const keys = page.getByRole("region", { name: "API keys" });
    await expect(keys.getByText("No keys yet")).toBeVisible();

    await keys.getByLabel("Name for a new key").fill("ci pipeline");
    await keys.getByRole("button", { name: "Create key" }).click();
    const secret = (await page.getByLabel("New API key", { exact: true }).innerText()).trim();
    expect(secret).toMatch(/^prs_sk_[A-Za-z0-9_-]{32}$/);
    await expect(keys.getByText("shown only once")).toBeVisible();

    // a server (no cookies, no Origin) can use it
    const ok = await request.post("/api/v1/predict", { data: { strokes: TRIANGLE, top_k: 3 }, headers: { Authorization: `Bearer ${secret}` } });
    expect(ok.status()).toBe(200);
    const body = await ok.json();
    expect(body.predictions).toHaveLength(3);
    expect(body.predictions[0].label).toBe("pizza");                 // the documented example, reproduced for real
    expect(Number(ok.headers()["ratelimit-remaining"])).toBeLessThan(Number(ok.headers()["ratelimit-limit"]));

    // a web page cannot: a secret key in front-end code is refused
    const fromBrowser = await page.evaluate(async ({ key, strokes }) => {
      const r = await fetch("/api/v1/predict", { method: "POST", headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" }, body: JSON.stringify({ strokes }) });
      return { status: r.status, code: (await r.json()).error.code };
    }, { key: secret, strokes: TRIANGLE });
    expect(fromBrowser).toEqual({ status: 403, code: "browser_not_allowed" });

    // the key is hidden once dismissed, and never comes back
    await keys.getByRole("button", { name: "I have saved it" }).click();
    await expect(page.getByText(secret)).toHaveCount(0);
    await page.reload();
    await expect(page.getByText(secret)).toHaveCount(0);
    const row = page.getByRole("table", { name: "Your API keys" }).locator("tr", { hasText: "ci pipeline" });
    await expect(row).toContainText(secret.slice(0, 11));
    await expect(row).toContainText("1 / 1000");                       // the call above was metered (the browser attempt was refused before counting)

    await row.getByRole("button", { name: /Usage for/ }).click();
    await expect(page.getByRole("img", { name: "Requests per day, last 14 days" })).toBeVisible();
    await expect(page.getByText(/Last 14 days: 1 request, 0 errors/)).toBeVisible();

    // revoke: effective immediately
    await row.getByRole("button", { name: /Revoke ci pipeline/ }).click();
    await row.getByRole("button", { name: "Revoke now" }).click();
    await expect(row).toContainText("revoked");
    const after = await request.post("/api/v1/predict", { data: { strokes: TRIANGLE }, headers: { Authorization: `Bearer ${secret}` } });
    expect(after.status()).toBe(401);
    expect(errors.filter((e) => !/401|403/.test(e)), errors.join("\n")).toEqual([]);
  });

  test.describe("on a third-party website", () => {
    const PAGE = `<!doctype html><title>customer site</title><body style="margin:20px">
        <div id="a"></div>
        <prescribble-canvas id="b" size="260" theme="dark"></prescribble-canvas>
        <script src="${API_ORIGIN}/widget/prescribble-widget.js"></script>
        <script>
          window.guesses = [];
          window.events = [];
          Prescribble.mount("#a", { size: 300, onGuess: (e) => window.guesses.push(e.top5[0].label), onReady: () => { window.ready = true; },
            onError: (e) => window.events.push("error: " + e.message) });
          document.getElementById("b").addEventListener("guess", (e) => { window.elementGuess = e.detail.top5[0].label; });
        </script>`;
    let customer: Server;
    let customerOrigin = "";
    // A real website on its own origin (random free port), like a customer's server. A fake in-browser document has no network
    // address, and browsers rightly refuse to let such a page reach localhost.
    test.beforeAll(async () => {
      customer = createServer((_, res) => { res.setHeader("content-type", "text/html; charset=utf-8"); res.end(PAGE); });
      await new Promise<void>((resolve) => customer.listen(0, "127.0.0.1", resolve));
      customerOrigin = `http://127.0.0.1:${(customer.address() as AddressInfo).port}`;
    });
    test.afterAll(() => new Promise<void>((resolve) => customer.close(() => resolve())));

    test("the widget works there and never sends the drawing anywhere", async ({ page }) => {
    const requests: Request[] = [];
    page.on("request", (r) => requests.push(r));
    const errors = watchErrors(page);

    await page.goto(customerOrigin);
    try {
      await page.waitForFunction(() => (window as unknown as { ready?: boolean }).ready === true, undefined, { timeout: 45_000 });
    } catch {
      const events = await page.evaluate(() => (window as unknown as { events?: string[] }).events);
      throw new Error(`the widget never became ready. widget errors: ${JSON.stringify(events)}; page errors: ${errors.join(" | ")}; requests: ${requests.map((r) => r.url()).join(", ")}`);
    }

    const canvas = page.locator("#a >> canvas.draw");
    const box = (await canvas.boundingBox())!;
    const at = ([x, y]: number[]) => ({ x: box.x + (x! / 255) * box.width, y: box.y + (y! / 255) * box.height });
    for (const s of HOUSE) {
      const first = at(s[0]!);
      await page.mouse.move(first.x, first.y);
      await page.mouse.down();
      for (const p of s.slice(1)) { const q = at(p); await page.mouse.move(q.x, q.y, { steps: 6 }); }
      await page.mouse.up();
    }
    await expect.poll(() => page.evaluate(() => (window as unknown as { guesses: string[] }).guesses.at(-1)), { timeout: 20_000 }).toBe("house");
    await expect(page.locator("#a").locator(".top")).toContainText("house");

    // the <prescribble-canvas> element works too
    const second = (await page.locator("#b >> canvas.draw").boundingBox())!;
    const at2 = ([x, y]: number[]) => ({ x: second.x + (x! / 255) * second.width, y: second.y + (y! / 255) * second.height });
    const tri = TRIANGLE[0]!;
    await page.mouse.move(at2(tri[0]!).x, at2(tri[0]!).y);
    await page.mouse.down();
    for (const p of tri.slice(1)) await page.mouse.move(at2(p).x, at2(p).y, { steps: 6 });
    await page.mouse.up();
    await expect.poll(() => page.evaluate(() => (window as unknown as { elementGuess?: string }).elementGuess), { timeout: 20_000 }).toBeTruthy();

    // privacy, proven from the network log: the widget only downloads files; it sends nothing
    const sent = requests.filter((r) => r.method() !== "GET" || r.postData());
    expect(sent.map((r) => `${r.method()} ${r.url()}`)).toEqual([]);
    const hosts = new Set(requests.map((r) => new URL(r.url()).origin));
    expect([...hosts].sort()).toEqual([API_ORIGIN, customerOrigin].sort());       // only the customer's own site and the widget host
    expect(errors, errors.join("\n")).toEqual([]);
  });
  });

  test("admin dashboard: only for operators, and the numbers are the server's", async ({ page, request }) => {
    const email = await signUp(page, "Ops Olivia");
    await page.goto("/admin");
    await expect(page.getByRole("heading", { name: "Admins only" })).toBeVisible();          // signing up never grants admin
    expect((await page.request.get("/api/v1/admin/metrics")).status()).toBe(403);

    makeAdmin(email);
    await page.goto("/admin");
    await expect(page.getByRole("heading", { name: "Operations" })).toBeVisible();
    const metrics = await (await page.request.get("/api/v1/admin/metrics")).json();
    expect(metrics.users.total).toBeGreaterThan(0);
    const tiles = page.locator(".tiles .stat");
    await expect(tiles.nth(0)).toContainText(String(metrics.users.total));
    await expect(tiles.nth(1)).toContainText(String(metrics.drawings.total));
    await expect(tiles.nth(3)).toContainText(String(metrics.api.active_keys));
    await expect(page.getByRole("img", { name: "API requests per day" })).toBeVisible();
    expect(JSON.stringify(metrics)).not.toContain("example.com");                          // owners are names, never emails
    expect(request).toBeTruthy();
  });
});
