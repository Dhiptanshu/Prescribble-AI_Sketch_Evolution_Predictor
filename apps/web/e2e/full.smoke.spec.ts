import { expect, test } from "@playwright/test";
import { HOUSE, draw, waitForModel, watchErrors } from "./helpers";

test.describe("full product (API serves the built app)", () => {
  test("landing page loads the model and shows measured numbers", async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("guesses your drawing");
    await waitForModel(page);
    const stats = page.locator(".stat b");
    await expect(stats).toHaveCount(4);
    for (let i = 0; i < 3; i++) await expect(stats.nth(i)).toHaveText(/^\d+\.\d%$/);   // read from the model's real test results
    const live = await (await page.request.get("/api/v1/model")).json();
    await expect(stats.nth(3)).toHaveText(String(live.classes.length));               // the live model's own class count
    await expect(page.locator(".top1 .name").first()).toBeVisible({ timeout: 30_000 });    // hero demo is predicting a real sketch
    expect(errors, errors.join("\n")).toEqual([]);          // includes: no 401 noise for a logged-out visitor
  });

  test("studio recognises a hand-drawn house as it is drawn", async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto("/studio");
    await waitForModel(page);
    await draw(page, HOUSE);
    await expect(page.locator(".top1 .name")).toHaveText("house", { timeout: 15_000 });
    await expect(page.locator(".toolbar .meta")).toContainText("2 strokes");
    await expect(page.locator(".bars li").first()).toContainText("house");
    expect(errors, errors.join("\n")).toEqual([]);
    await page.getByRole("button", { name: "Clear" }).click();
    await expect(page.getByText("Waiting for a stroke").first()).toBeVisible();
  });

  test("replay of a real held-out sketch reports when the AI got it", async ({ page }) => {
    await page.goto("/studio");
    await waitForModel(page);
    await page.getByRole("button", { name: "Watch real sketches" }).click();
    await page.getByRole("button", { name: "▶ Play" }).click();
    await expect(page.getByRole("status")).toContainText(/Correct in the Top-5|never/, { timeout: 40_000 });
  });

  test("AI challenge shows a target word and lets you give up", async ({ page }) => {
    await page.goto("/studio");
    await waitForModel(page);
    await page.getByRole("button", { name: "AI challenge" }).click();
    await expect(page.getByText(/Draw: /)).toBeVisible();
    await page.getByRole("button", { name: "Give up" }).click();
    await expect(page.getByRole("status")).toContainText("Nothing was drawn");
  });

  test("register, stay signed in across a reload, sign out, sign back in", async ({ page }) => {
    const errors = watchErrors(page);
    const email = `smoke.${Date.now()}@example.com`, password = "Smoke-Test-Passphrase-93";
    await page.goto("/register");
    await page.getByLabel("Display name").fill("Smoke Tester");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel(/Password/).fill(password);
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL(/\/studio$/);
    await expect(page.locator(".nav-right")).toContainText("Smoke Tester");

    await page.reload();
    await expect(page.locator(".nav-right")).toContainText("Smoke Tester");
    expect(await page.evaluate(() => document.cookie)).not.toContain("prescribble_session");   // httpOnly: invisible to scripts

    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByRole("banner").getByRole("link", { name: "Sign in" })).toBeVisible();

    await page.getByRole("banner").getByRole("link", { name: "Sign in" }).click();
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("definitely-the-wrong-one");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("alert")).toContainText("incorrect");
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.locator(".nav-right")).toContainText("Smoke Tester");
    // the one failed login above legitimately logs a 401 to the console; nothing else may
    expect(errors.filter((e) => !/401/.test(e)), errors.join("\n")).toEqual([]);
  });

  test("API contract: session endpoint, standard error shape, health", async ({ request }) => {
    expect(await (await request.get("/api/v1/auth/session")).json()).toEqual({ user: null });
    const bad = await request.get("/api/v1/me");
    expect(bad.status()).toBe(401);
    expect((await bad.json()).error.code).toBe("unauthenticated");
    expect(await (await request.get("/healthz")).json()).toEqual({ status: "ok" });
  });

  test("theme toggle switches between dark and light", async ({ page }) => {
    await page.goto("/");
    const before = await page.evaluate(() => document.documentElement.dataset.theme);
    await page.getByRole("button", { name: /Switch to/ }).click();
    const after = await page.evaluate(() => document.documentElement.dataset.theme);
    expect(after).not.toBe(before);
  });
});
