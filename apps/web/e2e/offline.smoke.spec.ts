import { expect, test } from "@playwright/test";
import { draw, waitForModel, watchErrors } from "./helpers";

// What a lab machine runs: the static bundle with NO backend. The Studio must work fully; accounts must be hidden, not broken.
test.describe("offline mode (static server, no backend)", () => {
  // the only expected console noise: the browser logs the missing /api session probe
  const benign = [/Failed to load resource.*404/];

  test("studio works and the app announces offline mode", async ({ page }) => {
    const errors = watchErrors(page, benign);
    await page.goto("/studio");
    await waitForModel(page);
    await expect(page.getByText("offline mode")).toBeVisible();
    await expect(page.getByRole("link", { name: "Sign in" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Create account" })).toHaveCount(0);

    await draw(page, [[[128, 40], [60, 210], [196, 210], [128, 40]]]);             // a triangle
    await expect(page.locator(".top1 .name")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator(".bars li")).toHaveCount(5);
    await expect(page.locator(".toolbar .meta")).toContainText("1 stroke");
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("a refresh on a deep link still works (SPA fallback)", async ({ page }) => {
    await page.goto("/studio");
    await page.reload();
    await waitForModel(page);
    await expect(page.getByRole("button", { name: "Free draw" })).toBeVisible();
  });

  test("login page explains that accounts need the server instead of failing", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Accounts unavailable" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Open the Studio" })).toBeVisible();
  });

  test("real-sketch replay works offline", async ({ page }) => {
    await page.goto("/studio");
    await waitForModel(page);
    await page.getByRole("button", { name: "Watch real sketches" }).click();
    await page.getByRole("button", { name: "▶ Play" }).click();
    await expect(page.getByRole("status")).toContainText(/Correct in the Top-5|never/, { timeout: 40_000 });
  });
});
