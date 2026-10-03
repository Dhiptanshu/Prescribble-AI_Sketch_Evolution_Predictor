import { expect, test, type Browser, type Page } from "@playwright/test";
import { waitForModel, watchErrors } from "./helpers";

type Stroke = [number, number][];
const PASSWORD = "Phase-Five-Passphrase-51";
const BASE = "http://127.0.0.1:8110";

/** Draw like a person: paced mouse movement, so the server's plausibility check accepts it. */
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

/** A separate browser profile, like another person's computer. */
async function person(browser: Browser, name = "person") {
  const context = await browser.newContext({ baseURL: BASE });
  const page = await context.newPage();
  const errors = watchErrors(page);
  page.on("response", (r) => { if (r.status() === 409) errors.push(`409 ${r.request().method()} ${r.url()}`); });
  return { name, context, page, errors };
}

test.describe("phase 5: classrooms", () => {
  test("two students and a teacher play a synchronised round, and the server scores it", async ({ browser, request }) => {
    test.setTimeout(150_000);          // five browser profiles, three of them running the model: slow on a busy machine
    const samples: { label: string; strokes: Stroke[] }[] = await (await request.get("/models/v1/samples.json")).json();
    const cats = samples.filter((s) => s.label === "cat");

    const teacher = await person(browser, "teacher");
    const t = teacher.page;
    await t.goto("/register");
    await t.getByLabel("Display name").fill("Ms Rivera");
    await t.getByLabel("Email").fill(`p5.${Date.now()}@example.com`);
    await t.getByLabel(/Password/).fill(PASSWORD);
    await t.getByRole("button", { name: "Create account" }).click();
    await expect(t).toHaveURL(/\/studio$/);

    // the teacher creates a room and gets a code to read out
    await t.getByRole("link", { name: "Classrooms" }).click();
    await expect(t.getByText("You have no rooms yet")).toBeVisible();
    await t.getByLabel("Room name").fill("Period 3 art");
    await t.getByRole("button", { name: "Create room" }).click();
    await expect(t).toHaveURL(/\/classroom\/\d+$/);
    const code = (await t.locator(".join-code").innerText()).trim();
    expect(code).toMatch(/^[A-HJKMNP-Z2-9]{6}$/);
    await expect(t.getByRole("status")).toHaveText(/live/);
    await expect(t.getByText("Nobody has joined yet")).toBeVisible();

    // two students join from their own browsers, with no account
    const ana = await person(browser, "ana"), ben = await person(browser, "ben");
    for (const [s, nick] of [[ana, "Ana"], [ben, "Ben"]] as const) {
      await s.page.goto(`/join/${code}`);
      await expect(s.page.getByLabel("Room code")).toHaveValue(code);
      await s.page.getByLabel("Nickname").fill(nick);
      await s.page.getByRole("button", { name: "Join" }).click();
      await expect(s.page).toHaveURL(/\/room\/\d+$/);
      await expect(s.page.getByRole("heading", { name: "Waiting for the teacher" })).toBeVisible();
    }
    const roster = t.getByRole("region", { name: "Students" });
    await expect(roster.getByText("Ana")).toBeVisible();                                   // pushed live, no reload
    await expect(roster.getByText("Ben")).toBeVisible();
    await expect(roster.getByText("2 joined")).toBeVisible();

    // a duplicate nickname is refused with a clear message
    const dup = await person(browser, "dup");
    await dup.page.goto(`/join/${code}`);
    await dup.page.getByLabel("Nickname").fill("ana");
    await dup.page.getByRole("button", { name: "Join" }).click();
    await expect(dup.page.getByRole("alert")).toContainText("already uses that nickname");

    // the teacher starts a round: both students get the word at once
    await waitForModel(ana.page); await waitForModel(ben.page);
    await t.getByLabel("Word").selectOption("cat");
    await t.getByLabel("Time").selectOption("120");
    await t.getByRole("button", { name: "Start round" }).click();
    for (const s of [ana, ben]) await expect(s.page.getByRole("heading", { name: "cat", level: 1 })).toBeVisible();
    await expect(t.getByRole("timer")).toBeVisible();

    // students draw (the AI guesses live in their own browser) and hand in
    await drawHuman(ana.page, cats[0]!.strokes);
    await expect(ana.page.getByRole("region", { name: "What the AI thinks" }).locator(".top1 .name")).not.toHaveText("");
    await ana.page.getByRole("button", { name: "Hand in" }).click();
    await expect(ana.page.getByText("Handed in. Scores appear when the round ends.")).toBeVisible();
    await expect(t.getByText("1 of 2 handed in").first()).toBeVisible();
    await drawHuman(ben.page, cats[1]!.strokes);
    await ben.page.getByRole("button", { name: "Hand in" }).click();
    await expect(t.getByText("2 of 2 handed in").first()).toBeVisible();

    // nothing is revealed while the round runs
    await expect(ana.page.getByRole("region", { name: /Round 1 results/ })).toHaveCount(0);
    await expect(t.getByRole("region", { name: /Round 1 results/ })).toHaveCount(0);

    // the teacher ends the round; everybody sees the same server-scored results
    await t.getByRole("button", { name: "End round now" }).click();
    for (const page of [t, ana.page, ben.page]) {
      const table = page.getByRole("table", { name: "Round 1 ranking" });
      await expect(table).toBeVisible({ timeout: 20_000 });
      await expect(table.getByRole("row")).toHaveCount(3);                                // header + two students
      await expect(table).toContainText("Ana");
      await expect(table).toContainText("Ben");
      await expect(page.getByRole("img", { name: "Ana’s drawing" })).toBeVisible();
      await expect(page.getByRole("img", { name: "Ben’s drawing" })).toBeVisible();
      await expect(page.getByText(/The AI (named the cat in|never recognised)/)).toBeVisible();
    }
    await expect(ana.page.getByRole("table", { name: "Round 1 ranking" }).getByText("(you)")).toBeVisible();
    await expect(t.getByRole("table", { name: "Total points" })).toBeVisible();

    // the room can run another round straight away, then closes
    await expect(t.getByRole("button", { name: "Start round" })).toBeVisible();
    await t.getByRole("button", { name: "Close room" }).click();
    await expect(t.getByText(/This room is closed/)).toBeVisible();
    await expect(ben.page.getByRole("heading", { name: "Room closed" })).toBeVisible();
    await expect(t.getByRole("button", { name: "Start round" })).toHaveCount(0);

    // a student who reloads is still in the room (the token lives in their browser)
    await ana.page.reload();
    await expect(ana.page.getByRole("heading", { name: "Room closed" })).toBeVisible();

    // the refused duplicate join is the only failed request in the whole session, and it was asked for
    expect(dup.errors.filter((e) => e.startsWith("409"))).toEqual([`409 POST ${BASE}/api/v1/rooms/join`]);
    dup.errors.length = 0;
    for (const p of [teacher, ana, ben, dup]) {
      expect(p.errors, p.errors.join("\n")).toEqual([]);
      await p.context.close();
    }
  });

  test("a stranger cannot open a teacher's room or a room they never joined", async ({ browser }) => {
    const stranger = await person(browser);
    await stranger.page.goto("/room/999999");
    await expect(stranger.page.getByRole("heading", { name: "You are not in this room" })).toBeVisible();
    await stranger.page.goto("/classroom/1");
    await expect(stranger.page).toHaveURL(/\/login$/);
    await stranger.context.close();
  });
});
