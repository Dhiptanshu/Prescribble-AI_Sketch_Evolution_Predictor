import { cpSync, existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { HOUSE, draw, waitForModel, watchErrors } from "./helpers";

const PASSWORD = "Phase-Six-Passphrase-61";
const models = join(resolve(dirname(fileURLToPath(import.meta.url)), ".."), "dist", "models");

async function signUp(page: import("@playwright/test").Page, name: string) {
  await page.goto("/register");
  await page.getByLabel("Display name").fill(name);
  await page.getByLabel("Email").fill(`p6.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.com`);
  await page.getByLabel(/Password/).fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/studio$/);
}

test.describe("phase 6: the model flywheel", () => {
  test("promoting a version in the registry changes which model the app loads, with no app change", async ({ page }) => {
    const registryFile = join(models, "registry.json");
    const original = readFileSync(registryFile, "utf-8");
    try {
      cpSync(join(models, "v1"), join(models, "v1b"), { recursive: true });                     // stands in for "a newly trained version"
      writeFileSync(registryFile, JSON.stringify({ ...JSON.parse(original), active: "v1b" }));  // what `registry promote` writes
      const model: string[] = [];
      page.on("request", (r) => { if (r.url().endsWith("sketch.onnx")) model.push(new URL(r.url()).pathname); });
      const cache = page.waitForResponse((r) => r.url().endsWith("/models/registry.json"));
      await page.goto("/studio");
      await waitForModel(page);
      expect(model).toEqual(["/models/v1b/sketch.onnx"]);                                         // the promoted version, nothing hard-coded
      expect((await cache).headers()["cache-control"]).toBe("no-cache");                           // so a promotion is seen on the next load

      writeFileSync(registryFile, original);                                                       // roll back
      model.length = 0;
      await page.reload();
      await waitForModel(page);
      expect(model).toEqual(["/models/v1/sketch.onnx"]);
    } finally {
      writeFileSync(registryFile, original);
      if (existsSync(join(models, "v1b"))) rmSync(join(models, "v1b"), { recursive: true, force: true });
    }
  });

  test("a person teaches the AI: consent first, one word at a time, contributions counted, withdrawable", async ({ page }) => {
    const errors = watchErrors(page);
    await signUp(page, "Teacher Tess");
    await waitForModel(page);

    await page.getByRole("link", { name: "Teach the AI" }).click();
    await expect(page.getByRole("heading", { name: "Teach the AI" })).toBeVisible();
    await expect(page.getByText(/Nothing is used for training unless you allow it/)).toBeVisible();     // consent comes first
    await page.getByRole("button", { name: "Allow it and start" }).click();

    const word = page.locator(".prompt h1");
    await expect(word).not.toHaveText("…");
    const first = (await word.innerText()).trim();
    const mine = page.getByRole("region", { name: "Your contribution" });
    await expect(mine.getByText("drawings from you")).toBeVisible();
    await expect(mine.locator("b").first()).toHaveText("0");

    await draw(page, HOUSE);
    await page.getByRole("button", { name: "Save and next" }).click();
    await expect(mine.locator("b").first()).toHaveText("1");                                       // counted from the server
    await expect(word).not.toHaveText(first);                                                      // and never the same word twice in a row

    // contributions stay out of the gallery
    await page.getByRole("link", { name: "Gallery" }).click();
    await expect(page.getByText(/No drawings yet|nothing saved/i).or(page.getByRole("heading", { name: /Gallery/ })).first()).toBeVisible();
    expect(await page.locator("a.tile").count()).toBe(0);

    // withdraw everything
    await page.getByRole("link", { name: "Teach the AI" }).click();
    page.once("dialog", (d) => void d.accept());
    await page.getByRole("button", { name: "Delete everything I contributed" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Deleted 1." })).toBeVisible();
    await expect(mine.locator("b").first()).toHaveText("0");
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("a saved Studio drawing is only confirmed when the person says so", async ({ page }) => {
    await signUp(page, "Careful Cleo");
    await waitForModel(page);
    await draw(page, HOUSE);
    const save = page.getByRole("region", { name: "Save" });
    const box = save.getByLabel("I checked: this label is right");
    await expect(box).not.toBeChecked();                                                           // the AI's own guess is never a confirmation
    await save.getByRole("button", { name: "Save drawing" }).click();
    await expect(save.getByRole("status")).toContainText("Saved");
    const unconfirmed = await page.evaluate(async () => (await (await fetch("/api/v1/drawings")).json()).items[0]);
    expect(unconfirmed.label_confirmed).toBe(false);
    expect(unconfirmed.input_type).toBe("mouse");                                                  // captured from the real pointer

    await page.getByRole("button", { name: "Clear" }).click();
    await draw(page, HOUSE);
    await save.getByLabel("I checked: this label is right").check();
    await save.getByRole("button", { name: "Save drawing" }).click();
    await expect(save.getByRole("status")).toContainText("Saved");
    const confirmed = await page.evaluate(async () => (await (await fetch("/api/v1/drawings")).json()).items[0]);
    expect(confirmed.label_confirmed).toBe(true);
  });
});
