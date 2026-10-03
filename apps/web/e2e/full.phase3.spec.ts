import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { liveSamples, waitForModel, watchErrors } from "./helpers";

type Stroke = [number, number][];
interface Sample { label: string; strokes: Stroke[] }

const PASSWORD = "Phase-Three-Passphrase-31";

async function sketchOf(request: APIRequestContext, k = 0): Promise<{ target: string; strokes: Stroke[] }> {
  const today = await (await request.get("/api/v1/challenge/today")).json();
  const samples: Sample[] = await liveSamples(request);
  const matching = samples.filter((s) => s.label === today.target);
  return { target: today.target, strokes: matching[k % matching.length]!.strokes };
}

/** Draw like a person: paced mouse movement (a few seconds in total), so the server's plausibility check passes. */
async function drawHuman(page: Page, strokes: Stroke[]) {
  const box = await page.locator("canvas.draw").boundingBox();
  if (!box) throw new Error("drawing canvas not found");
  const at = ([x, y]: [number, number]) => ({ x: box.x + (x / 255) * box.width, y: box.y + (y / 255) * box.height });
  for (const s of strokes) {
    const first = at(s[0]!);
    await page.mouse.move(first.x, first.y);
    await page.mouse.down();
    for (const p of s.slice(1)) { const q = at(p); await page.mouse.move(q.x, q.y, { steps: 2 }); await page.waitForTimeout(25); }
    await page.mouse.up();
    await page.waitForTimeout(120);
  }
}

/** Dispatch the whole drawing in one synchronous burst: what a script would do. */
async function drawInstantly(page: Page, strokes: Stroke[]) {
  await page.evaluate((strokes) => {
    const c = document.querySelector("canvas.draw") as HTMLCanvasElement, r = c.getBoundingClientRect();
    const fire = (type: string, x: number, y: number) => c.dispatchEvent(new PointerEvent(type, { clientX: r.left + (x / 255) * r.width, clientY: r.top + (y / 255) * r.height, pointerId: 1, bubbles: true, pointerType: "mouse" }));
    for (const s of strokes) { fire("pointerdown", ...s[0]!); for (const p of s.slice(1)) fire("pointermove", ...p); fire("pointerup", ...s[s.length - 1]!); }
  }, strokes);
}

async function signUp(page: Page, name: string) {
  await page.goto("/register");
  await page.getByLabel("Display name").fill(name);
  await page.getByLabel("Email").fill(`p3.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.com`);
  await page.getByLabel(/Password/).fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/studio$/);
}

test.describe("phase 3: daily challenge", () => {
  test("a visitor sees today's word and the board, and is asked to sign in to play", async ({ page, request }) => {
    const errors = watchErrors(page);
    const { target } = await sketchOf(request);
    await page.goto("/challenge");
    await waitForModel(page);
    await expect(page.getByRole("heading", { name: target, level: 1 })).toBeVisible();
    await expect(page.getByLabel("Time until the next word")).toHaveText(/^\d\d:\d\d:\d\d$/);
    await expect(page.getByRole("link", { name: "Sign in to play" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Submit attempt" })).toHaveCount(0);
    await expect(page.getByRole("region", { name: "Leaderboard" })).toBeVisible();
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("score an attempt, see it ranked, use all attempts, change privacy", async ({ page, request }) => {
    test.setTimeout(150_000);          // three server-scored attempts, each drawn by hand: close to the default budget on a busy machine
    const errors = watchErrors(page);
    const name = `Scorer ${Date.now() % 100000}`;
    await signUp(page, name);
    const { target, strokes } = await sketchOf(request);

    await page.goto("/challenge");
    await waitForModel(page);
    await expect(page.getByLabel("Your attempt").getByText("3 of 3 left")).toBeVisible();

    // attempt 1: drawn like a person, scored by the server
    await drawHuman(page, strokes);
    await expect(page.locator(".top1 .name")).toBeVisible({ timeout: 15_000 });        // live preview from the in-browser model
    await page.getByRole("button", { name: "Submit attempt" }).click();
    const result = page.getByRole("region", { name: "Result" });
    await expect(result).toBeVisible({ timeout: 30_000 });
    const score = Number(await result.getByLabel("Score").innerText());
    expect(score % 5).toBe(0);
    expect(score).toBeGreaterThanOrEqual(0);
    expect(score).toBeLessThanOrEqual(100);
    await expect(result).toContainText("verified by the server");
    await expect(result).not.toContainText("not counted");

    // the leaderboard shows me, highlighted, with the same score
    const board = page.getByRole("region", { name: "Leaderboard" });
    const mine = board.locator("tr[aria-current='true']");
    await expect(mine).toContainText(name);
    await expect(mine).toContainText(String(score));
    await expect(page.getByLabel("Your attempt").getByText("2 of 3 left")).toBeVisible();

    // attempts 2 and 3, then the board locks
    await page.getByRole("button", { name: /Try again/ }).click();
    await drawHuman(page, (await sketchOf(request, 1)).strokes);
    await page.getByRole("button", { name: "Submit attempt" }).click();
    await expect(result).toContainText("Attempt 2", { timeout: 30_000 });
    await page.getByRole("button", { name: /Try again/ }).click();
    await drawHuman(page, (await sketchOf(request, 2)).strokes);
    await page.getByRole("button", { name: "Submit attempt" }).click();
    await expect(result).toContainText("Attempt 3", { timeout: 30_000 });
    await expect(page.getByText("That was your last attempt today")).toBeVisible();
    await expect(page.getByRole("button", { name: /Try again/ })).toHaveCount(0);

    // reloading keeps the state (it comes from the server, not the page)
    await page.reload();
    await waitForModel(page);
    await expect(page.getByText(/You have used all 3 attempts today/)).toBeVisible();
    expect((await (await page.request.get("/api/v1/challenge/today")).json()).me.attempts_used).toBe(3);

    // privacy: hide my name; I keep my place but show as Anonymous
    await page.getByRole("link", { name: "Account settings" }).click();
    await expect(page).toHaveURL(/\/settings$/);
    await expect(page.getByLabel("Show my name on the leaderboard")).toBeChecked();
    await page.locator("label[for=show-lb]").click();                                      // click the visible switch, as a person would
    await expect(page.getByLabel("Show my name on the leaderboard")).not.toBeChecked();
    await page.goto("/challenge");
    await waitForModel(page);
    const hidden = page.getByRole("region", { name: "Leaderboard" }).locator("tr[aria-current='true']");
    await expect(hidden).toContainText("Anonymous");
    await expect(page.getByRole("region", { name: "Leaderboard" })).not.toContainText(name);
    expect(target).toBeTruthy();
    expect(errors.filter((e) => !/401|409/.test(e)), errors.join("\n")).toEqual([]);
  });

  test("an instant, scripted submission is kept off the leaderboard", async ({ page, request }) => {
    const name = `Bot ${Date.now() % 100000}`;
    await signUp(page, name);
    const { strokes } = await sketchOf(request);
    await page.goto("/challenge");
    await waitForModel(page);
    await drawInstantly(page, strokes);
    await page.getByRole("button", { name: "Submit attempt" }).click();
    const result = page.getByRole("region", { name: "Result" });
    await expect(result).toContainText("not counted on the leaderboard", { timeout: 30_000 });
    await expect(page.getByRole("region", { name: "Leaderboard" })).not.toContainText(name);
  });

  test("account settings: export my data and delete my account", async ({ page }) => {
    await signUp(page, "Leaver Lou");
    await page.goto("/settings");
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download my data" }).click();
    expect((await download).suggestedFilename()).toBe("prescribble-my-data.json");

    await page.getByRole("button", { name: "Delete my account" }).click();
    await page.getByLabel("Type your password to confirm").fill("not-my-password-123");
    await page.getByRole("button", { name: "Delete everything" }).click();
    await expect(page.getByRole("alert")).toContainText("incorrect");
    await page.getByLabel("Type your password to confirm").fill(PASSWORD);
    await page.getByRole("button", { name: "Delete everything" }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("banner").getByRole("link", { name: "Sign in" })).toBeVisible();
  });
});
