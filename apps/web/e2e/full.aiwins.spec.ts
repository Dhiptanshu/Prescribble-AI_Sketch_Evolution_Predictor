import { expect, test } from "@playwright/test";
import { drawKeepingPenDown, liveSamples, waitForModel } from "./helpers";

test.describe("AI challenge: the AI wins fairly", () => {
  test.setTimeout(300_000);

  test("a popup says the AI wins and the pen stops drawing mid-stroke", async ({ page }) => {
    const samples = await liveSamples(page.request);
    await page.goto("/studio");
    await waitForModel(page);
    await page.getByRole("button", { name: "AI challenge" }).click();
    const dialog = page.getByRole("dialog", { name: "AI wins!" });
    const ink = page.locator(".toolbar .meta");

    let won = false;
    for (let round = 0; round < 15 && !won; round++) {
      if (round > 0) await page.getByRole("button", { name: "New word" }).click();
      const target = await page.locator(".banner b").first().innerText();
      const sample = samples.find((s) => s.label === target);
      if (!sample) continue;                                            // every class of the live model has real samples; skip defensively
      await drawKeepingPenDown(page, sample.strokes);                    // the pen is still down at the end of the last stroke
      try { await expect(dialog).toBeVisible({ timeout: 5_000 }); } catch { await page.mouse.up(); continue; }   // the AI did not get this one: another word
      won = true;

      await expect(dialog).toContainText(target);
      await page.waitForTimeout(400);                                   // let the pop-in animation finish
      const modal = (await page.locator(".modal").boundingBox())!, view = page.viewportSize()!;
      expect(Math.abs(modal.x + modal.width / 2 - view.width / 2), "the popup is centred horizontally").toBeLessThan(4);   // it once drew in the bottom right, inside a blurred card
      expect(Math.abs(modal.y + modal.height / 2 - view.height / 2), "the popup is centred vertically").toBeLessThan(4);
      await expect(page.getByRole("button", { name: "Next word" })).toBeFocused();
      const frozen = await ink.innerText();
      const box = (await page.locator("canvas.draw").boundingBox())!;
      for (let i = 0; i < 12; i++) await page.mouse.move(box.x + 20 + i * 15, box.y + 30 + (i % 4) * 40, { steps: 3 });    // the pen keeps moving: nothing more is drawn
      await expect(ink).toHaveText(frozen);
      await page.mouse.up();
      await expect(ink).toHaveText(frozen);

      await page.keyboard.press("Escape");
      await expect(dialog).toBeHidden();
      await expect(page.getByRole("status")).toContainText(`The AI recognised ${target}`);
      await expect(page.getByText("AI got it").locator("xpath=preceding-sibling::b")).toHaveText("1");
    }
    expect(won, "the AI should win at least once in 15 rounds with real sketches").toBe(true);

    await page.getByRole("button", { name: "New word" }).click();         // a new round starts with a clean board and no popup
    await expect(dialog).toBeHidden();
    await expect(ink).toContainText("0 strokes");
  });
});
