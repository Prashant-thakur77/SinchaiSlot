import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const SCREENS = ["/", "/twin", "/planner", "/phone", "/drive", "/ledger", "/lab", "/trace", "/hisaab", "/mitra"];

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

test("cloud at 13:40 re-plans with reasons and callbacks", async ({ page, request }) => {
  await request.post("/api/demo/reset");
  await page.goto("/planner");
  await page.getByRole("button", { name: "Jump to 13:45" }).click();
  await expect(page.getByText(/v\d+ · 13:4/)).toBeVisible({ timeout: 30_000 });
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
