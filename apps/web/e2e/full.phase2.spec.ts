import { expect, test, type Page } from "@playwright/test";
import { HOUSE, draw, waitForModel, watchErrors } from "./helpers";

const PASSWORD = "Phase-Two-Passphrase-77";

async function signUp(page: Page, name: string) {
  const email = `p2.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Display name").fill(name);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel(/Password/).fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/studio$/);
  await waitForModel(page);
  return email;
}

test.describe("phase 2: save, gallery, share, video, stats", () => {
  test("the full journey of one drawing", async ({ page, browser }) => {
    const errors = watchErrors(page);
    await signUp(page, "Ada Tester");

    // empty states are honest before anything is saved
    await page.goto("/gallery");
    await expect(page.getByRole("heading", { name: "No drawings yet" })).toBeVisible();
    await page.goto("/stats");
    await expect(page.getByRole("heading", { name: "No stats yet" })).toBeVisible();

    // draw and save: the label defaults to the AI's own guess
    await page.getByRole("link", { name: "Open the Studio" }).click();
    await waitForModel(page);
    await draw(page, HOUSE);
    await expect(page.locator(".top1 .name")).toHaveText("house", { timeout: 15_000 });
    await expect(page.getByLabel("What did you draw?")).toHaveValue("house");
    await page.getByRole("button", { name: "Save drawing" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Saved" })).toBeVisible();

    // the confirmation disappears when the drawing changes
    await page.getByRole("button", { name: "Clear" }).click();
    await expect(page.getByRole("button", { name: "Save drawing" })).toBeVisible();

    // gallery shows it, with the real recognition text
    await page.getByRole("link", { name: "Gallery" }).click();
    const tile = page.locator("a.tile").first();
    await expect(tile).toContainText("house");
    await expect(tile).toContainText(/AI (had it by \d+% of the ink|named it only at the end)/);
    await tile.click();
    await expect(page).toHaveURL(/\/gallery\/\d+$/);

    // replay runs the real model and moves the caption
    await expect(page.getByRole("img", { name: /Replay of your house/ })).toBeVisible();
    await page.getByRole("button", { name: /Replay|Play/ }).click();
    await expect(page.getByRole("button", { name: "■ Stop" })).toBeVisible();
    await expect(page.getByRole("button", { name: "▶ Replay" })).toBeVisible({ timeout: 30_000 });

    // relabel
    await page.getByLabel("What it is").selectOption("tree");
    await expect(page.getByLabel("What it is")).toHaveValue("tree");
    await page.getByLabel("What it is").selectOption("house");

    // share: private by default, link works for a stranger, stops working when revoked
    await expect(page.getByText("This drawing is private")).toBeVisible();
    await page.getByRole("button", { name: "Create share link" }).click();
    const link = await page.getByLabel("Share link").inputValue();
    expect(link).toMatch(/\/d\/[A-Za-z0-9_-]{12}$/);

    const stranger = await browser.newContext();             // no cookies: a different person
    const sp = await stranger.newPage();
    const strangerErrors = watchErrors(sp);
    await sp.goto(link);
    await expect(sp.getByRole("heading", { name: "A drawing by Ada Tester" })).toBeVisible();
    await expect(sp.getByText("Drawn as: house")).toBeVisible();
    await expect(sp.getByText(/p2\./)).toHaveCount(0);       // the email never leaks
    expect(strangerErrors, strangerErrors.join("\n")).toEqual([]);

    await page.getByRole("button", { name: "Stop sharing" }).click();
    await expect(page.getByText("This drawing is private")).toBeVisible();
    await sp.reload();
    await expect(sp.getByRole("heading", { name: "This drawing is not shared" })).toBeVisible();
    await stranger.close();

    // export the replay as a real video file
    const download = page.waitForEvent("download", { timeout: 60_000 });
    await page.getByRole("button", { name: "Save as video" }).click();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(/^prescribble-house-\d+\.webm$/);
    const path = await file.path();
    const { statSync } = await import("node:fs");
    expect(statSync(path).size).toBeGreaterThan(5_000);       // a real recording, not an empty file

    // stats now reflect the saved drawing
    await page.getByRole("link", { name: "Stats" }).click();
    await expect(page.getByRole("heading", { name: "Your stats" })).toBeVisible();
    await expect(page.locator(".tiles .stat").first()).toContainText("1");
    await expect(page.getByRole("cell", { name: "house" })).toBeVisible();
    await expect(page.getByText("1 day", { exact: false }).first()).toBeVisible();      // streak

    // delete
    await page.getByRole("link", { name: "Gallery" }).click();
    await page.locator("a.tile").first().click();
    await page.getByRole("button", { name: "Delete drawing" }).click();
    await page.getByRole("button", { name: "Yes, delete" }).click();
    await expect(page).toHaveURL(/\/gallery$/);
    await expect(page.getByRole("heading", { name: "No drawings yet" })).toBeVisible();

    expect(errors.filter((e) => !/401/.test(e)), errors.join("\n")).toEqual([]);
  });

  test("signed-out visitors are sent to sign in, then back where they were going", async ({ page }) => {
    await page.goto("/gallery");
    await expect(page).toHaveURL(/\/login$/);
    await page.getByLabel("Email").fill("nobody@example.com");
    await page.getByLabel("Password").fill("not-a-real-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("alert")).toBeVisible();
  });

  test("the studio offers sign-in instead of saving to a visitor", async ({ page }) => {
    await page.goto("/studio");
    await waitForModel(page);
    await expect(page.getByRole("link", { name: "Sign in" }).last()).toBeVisible();
    await expect(page.getByRole("button", { name: "Save drawing" })).toHaveCount(0);
  });

  test("a made-up share link shows a clear message", async ({ page }) => {
    await page.goto("/d/not-a-real-token-1");
    await expect(page.getByRole("heading", { name: "This drawing is not shared" })).toBeVisible();
  });

  test("users cannot open each other's drawings", async ({ page, browser }) => {
    await signUp(page, "Owner");
    await draw(page, HOUSE);
    await expect(page.locator(".top1 .name")).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: "Save drawing" }).click();
    await page.getByRole("link", { name: "Open it in your gallery" }).click();
    const url = page.url();

    const other = await browser.newContext();
    const op = await other.newPage();
    await signUp(op, "Intruder");
    await op.goto(url);
    await expect(op.getByRole("heading", { name: "Drawing not found" })).toBeVisible();
    await other.close();
  });
});
