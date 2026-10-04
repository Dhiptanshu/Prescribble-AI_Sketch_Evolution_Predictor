import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { waitForModel } from "./helpers";

const PASSWORD = "Accessibility-Passphrase-71";
const RULES = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

/** Scan the current page against WCAG 2.1 A and AA in the theme it is showing. */
async function scan(page: Page, where: string) {
  const result = await new AxeBuilder({ page }).withTags(RULES).analyze();
  const found = result.violations.map((v) => `${v.id} (${v.impact}): ${v.help} -> ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
  expect(found, `${where}\n${found.join("\n")}`).toEqual([]);
}

async function bothThemes(page: Page, path: string, ready?: () => Promise<void>) {
  for (const theme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto(path);
    await page.evaluate((t) => { document.documentElement.dataset.theme = t; }, theme);
    if (ready) await ready();
    await page.waitForTimeout(400);
    await scan(page, `${path} (${theme} theme)`);
  }
}

test.describe("accessibility: WCAG 2.1 A and AA, both themes", () => {
  test("pages a visitor sees", async ({ page }) => {
    test.setTimeout(180_000);
    await bothThemes(page, "/", () => waitForModel(page));
    await bothThemes(page, "/studio", () => waitForModel(page));
    await bothThemes(page, "/challenge", () => waitForModel(page));
    await bothThemes(page, "/developers", () => waitForModel(page));
    await bothThemes(page, "/join");
    await bothThemes(page, "/login");
    await bothThemes(page, "/register");
  });

  test("pages behind an account", async ({ page }) => {
    test.setTimeout(240_000);
    await page.goto("/register");
    await page.getByLabel("Display name").fill("Access Checker");
    await page.getByLabel("Email").fill(`a11y.${Date.now()}@example.com`);
    await page.getByLabel(/Password/).fill(PASSWORD);
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL(/\/studio$/);
    await waitForModel(page);
    for (const path of ["/gallery", "/stats", "/settings", "/classroom", "/teach"]) await bothThemes(page, path);
  });
});
