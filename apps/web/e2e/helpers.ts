import { expect, type APIRequestContext, type Page } from "@playwright/test";

/** Collects console errors and uncaught exceptions so a test can assert the page was clean. */
export function watchErrors(page: Page, ignore: RegExp[] = []) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error" && !ignore.some((r) => r.test(m.text()))) errors.push(`console: ${m.text()}`);
  });
  return errors;
}

/** Draw polylines in the model's 0..255 frame with real mouse input. */
export async function draw(page: Page, strokes: [number, number][][]) {
  const box = await page.locator("canvas.draw").boundingBox();
  if (!box) throw new Error("drawing canvas not found");
  const at = ([x, y]: [number, number]) => ({ x: box.x + (x / 255) * box.width, y: box.y + (y / 255) * box.height });
  for (const s of strokes) {
    const first = at(s[0]!);
    await page.mouse.move(first.x, first.y);
    await page.mouse.down();
    for (const p of s.slice(1)) { const q = at(p); await page.mouse.move(q.x, q.y, { steps: 6 }); }
    await page.mouse.up();
  }
}

export const HOUSE: [number, number][][] = [
  [[60, 120], [60, 210], [200, 210], [200, 120], [60, 120]],     // walls
  [[50, 125], [130, 55], [210, 125]],                            // roof
];

export async function waitForModel(page: Page) {
  await expect(page.getByText(/model ready/)).toBeVisible({ timeout: 40_000 });
}

/** Real held-out QuickDraw sketches of the LIVE model version (models/registry.json says which one), as shipped with the web build. */
export async function liveSamples(request: APIRequestContext): Promise<{ label: string; strokes: [number, number][][] }[]> {
  const { active } = await (await request.get("/models/registry.json")).json();
  return (await request.get(`/models/${active}/samples.json`)).json();
}
