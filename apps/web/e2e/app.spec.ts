import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const SCREENS = ["/", "/twin", "/planner", "/phone", "/drive", "/ledger", "/lab", "/trace", "/hisaab", "/mitra", "/cluster", "/passport/P2", "/rollout", "/judge"];

test.beforeAll(async ({ request }) => {
  await request.post("/api/demo/reset");
});

for (const path of SCREENS) {
  test(`${path} loads without console errors and passes axe @mobile`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(800);
    expect(errors, errors.join("\n")).toEqual([]);
    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    const serious = axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${v.id}: ${v.nodes.length} nodes`)).toEqual([]);
  });
}

test("farmer books by missed call; nothing is booked before the yes", async ({ page, request }) => {
  await request.post("/api/demo/reset");
  await page.goto("/phone");
  await page.getByRole("button", { name: "Missed call" }).click();
  await expect(page.getByText("Waiting for confirmation")).toBeVisible();
  let f = await (await request.get("/api/farmers/H01")).json();
  expect(f.bookings.length).toBe(0);
  await page.getByRole("group", { name: "Keypad" }).getByRole("button", { name: "1", exact: true }).click();
  await expect(page.getByText("confirmed by farmer")).toBeVisible();
  f = await (await request.get("/api/farmers/H01")).json();
  expect(f.bookings.length).toBe(1);
});

test("farmer can answer by speaking, and Saathi is read aloud", async ({ page, request }) => {
  await request.post("/api/demo/reset");
  // The browser's own recogniser and voices need a microphone and audio, so both are stood in for here.
  await page.addInitScript(() => {
    const w = window as unknown as Record<string, unknown>;
    w.spoken = [];
    w.SpeechRecognition = class {
      onresult: ((e: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      start() { setTimeout(() => { this.onresult?.({ results: [[{ transcript: "हाँ" }]] }); this.onend?.(); }, 50); }
      stop() {}
    };
    w.SpeechSynthesisUtterance = class { constructor(public text: string) {} };
    Object.defineProperty(window, "speechSynthesis", { value: {
      getVoices: () => [{ lang: "hi-IN" }], cancel() {}, speak: (u: { text: string }) => (w.spoken as string[]).push(u.text),
      addEventListener() {}, removeEventListener() {},
    } });
  });
  await page.goto("/phone");
  await page.getByRole("button", { name: "Hear Saathi" }).click();
  await page.getByRole("button", { name: "Missed call" }).click();
  await expect(page.getByText("Waiting for confirmation")).toBeVisible();
  await page.getByRole("button", { name: "Speak", exact: true }).click();
  await expect(page.getByText("confirmed by farmer")).toBeVisible();
  const f = await (await request.get("/api/farmers/H01")).json();
  expect(f.bookings.length).toBe(1);
  expect((await page.evaluate(() => (window as unknown as { spoken: string[] }).spoken)).length).toBeGreaterThanOrEqual(2);
});

test("cloud at 13:40 re-plans with reasons and callbacks", async ({ page, request }) => {
  await request.post("/api/demo/reset");
  await page.goto("/planner");
  await page.getByRole("button", { name: "Jump to 13:45" }).click();
  await expect(page.getByText(/13:4\d · plan v\d+/)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/less sun now expected/).first()).toBeVisible();
  const cbs = await (await request.get("/api/channels/callbacks")).json();
  expect(cbs.length).toBeGreaterThan(0);
});

test("Saur Mitra app is Hindi first and switches to English @mobile", async ({ page }) => {
  await page.goto("/mitra");
  await expect(page.getByText("सौर मित्र")).toBeVisible();
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByText("Saur Mitra", { exact: true })).toBeVisible();
});

test("cluster shows three pumps and a Pump Passport with a scorecard", async ({ page }) => {
  await page.goto("/cluster");
  await expect(page.getByText("Chakhaji Saur Pump 3 (simulated)")).toBeVisible();
  await page.getByRole("link", { name: "Pump Passport →" }).first().click();
  await expect(page.getByRole("img", { name: /Scorecard \d+ of 100/ })).toBeVisible();
});

test("Saur Mitra reads the sample soil card and applies it @mobile", async ({ page }) => {
  await page.goto("/mitra");
  await page.getByRole("button", { name: "मिट्टी" }).click();
  await page.getByRole("button", { name: "नमूना कार्ड पढ़ें" }).click();
  await page.getByRole("button", { name: "खेत पर लागू करें" }).click();
  await expect(page.getByRole("status")).toContainText("72 mm");
});

test("rollout matches the published proof and reacts to a site with no machine", async ({ page, request }) => {
  const proof = await (await request.get("/api/proof")).json();
  await page.goto("/rollout");
  await page.getByRole("button", { name: "Buy a new one" }).click();
  await page.getByRole("button", { name: "A paid Saur Mitra" }).click();
  await page.getByRole("slider", { name: /paid by subsidy/ }).fill("0");
  await page.getByRole("slider", { name: /Bookings/ }).fill("1");
  const years = async () => parseFloat(await page.getByTestId("payback").innerText());
  // Same inputs as the proof run: 6 lakh, no subsidy, paid operator.
  expect(Math.abs((await years()) - proof.policies.D.payback_years.p50)).toBeLessThan(0.15);
  const before = await years();
  await page.getByRole("checkbox", { name: /three-phase/ }).uncheck();
  await expect(page.getByText("the mill and cutter earn nothing")).toBeVisible();
  expect(await years()).toBeGreaterThan(before);
});

test("Pump Doctor names the cause of each fault", async ({ page }) => {
  await page.goto("/drive");
  for (const [btn, text] of [["Dust builds up", "Wash them"], ["Bearing wears", "bearing"], ["Water drops", "getting deeper"], ["Nothing wrong", "when it was new"]]) {
    await page.getByRole("button", { name: btn }).click();
    await expect(page.getByRole("status").filter({ hasText: text })).toBeVisible();
  }
});

test("ledger chain verifies from the UI", async ({ page }) => {
  await page.goto("/ledger");
  await page.getByRole("button", { name: "Verify the whole chain" }).click();
  await expect(page.getByRole("status")).toContainText("chain intact");
});

test.describe("reduced motion", () => {
  test.use({ reducedMotion: "reduce" });
  test("story shows its content without animation", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Solar pumps put about/ })).toBeVisible();
    await expect(page.getByRole("img", { name: /Solar power on the demo day/ })).toBeAttached({ timeout: 15_000 });
  });
});
