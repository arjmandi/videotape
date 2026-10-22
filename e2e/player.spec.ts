// The player's own promises (spec §8, S2, M1 exit): keyboard-only use, screen-reader
// names, alignment of facts over the picture, held input during transitions,
// reconnect with resume, and mobile basics.
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { expectHead, graph, open, pathTo, signIn, take } from "./helpers";

test("keyboard only: sign in, open the report, go back with Escape", async ({ page }, info) => {
  test.skip(info.project.name === "tablet", "covered by the desktop and phone runs");
  await open(page);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Sign in" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expectHead(page, "login/form");
  await expect(page.getByRole("heading", { level: 1, name: "Welcome back" })).toBeFocused();

  await page.keyboard.press("Tab");
  await expect(page.getByRole("textbox", { name: "Username" })).toBeFocused();
  await page.keyboard.type("ada");
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Password")).toBeFocused();
  await page.keyboard.type("lovelace");
  await page.keyboard.press("Enter");
  await expectHead(page, "dashboard/home");

  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Open report" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expectHead(page, "report/view");
  await expect(page.getByRole("heading", { level: 1, name: "Views, last 30 days" })).toBeFocused();
  await expect(page.getByRole("img", { name: "Views per day, last 30 days" })).toBeVisible();

  await page.keyboard.press("Escape");
  await expectHead(page, "dashboard/home");
});

test("every control is found by role and accessible name", async ({ page }) => {
  await open(page);
  await expect(page.getByRole("heading", { level: 1, name: "Interfaces, played." })).toBeVisible();
  await expect(page.getByRole("button", { name: "Read the docs" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Source on GitHub" })).toBeVisible();
  await page.getByRole("link", { name: "Sign in" }).click();
  await expectHead(page, "login/form");
  await expect(page.getByRole("textbox", { name: "Username" })).toBeVisible();
  await expect(page.getByLabel("Password")).toHaveAttribute("type", "password");
  await expect(page.getByLabel("Password")).toHaveAttribute("autocomplete", "current-password");
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Forgot password?" })).toBeVisible();
  await expect(page.getByRole("main")).toBeVisible();
});

for (const node of graph.nodes) {
  test(`axe finds no serious problems on ${node}`, async ({ page }) => {
    await open(page);
    for (const step of pathTo(node)) {
      await take(page, step);
      await expectHead(page, step.to!);
    }
    const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    const serious = result.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
  });
}

test("content nodes sit on their regions over the picture", async ({ page }) => {
  await open(page);
  await page.getByRole("link", { name: "Sign in" }).click();
  await expectHead(page, "login/form");
  const stage = (await page.locator(".vt-stage").boundingBox())!;
  const content = await page.evaluate(() =>
    (window as unknown as { videotape: { current: { content: Array<{ id: string; rect: number[] }> } } }).videotape.current.content);
  expect(content.length).toBeGreaterThan(5);
  for (const c of content) {
    const box = (await page.locator(`.vt-content [data-vt-id="${c.id}"]`).boundingBox())!;
    const [x, y, w, h] = c.rect as [number, number, number, number];
    expect(Math.abs(box.x - (stage.x + x * stage.width)), `${c.id} x`).toBeLessThanOrEqual(1);
    expect(Math.abs(box.y - (stage.y + y * stage.height)), `${c.id} y`).toBeLessThanOrEqual(1);
    expect(Math.abs(box.width - w * stage.width), `${c.id} w`).toBeLessThanOrEqual(1);
    expect(Math.abs(box.height - h * stage.height), `${c.id} h`).toBeLessThanOrEqual(1);
  }
  // The scene fills the stage, and the safe area is inside the window.
  const scene = (await page.locator(".vt-scene").first().boundingBox())!;
  expect(scene).toEqual(stage);
  const vp = page.viewportSize()!;
  expect(stage.x + stage.width * 0.06).toBeGreaterThanOrEqual(0);
  expect(stage.x + stage.width * 0.94).toBeLessThanOrEqual(vp.width + 0.5);
});

test("holds input while a transition is in flight, then lets go", async ({ page }) => {
  let delay = 0;
  await page.routeWebSocket(/\/vtp$/, (ws) => {
    const server = ws.connectToServer();
    server.onMessage((m) => void setTimeout(() => ws.send(m), delay));
    ws.onMessage((m) => server.send(m));
  });
  await open(page);
  delay = 700;
  await page.getByRole("link", { name: "Sign in" }).click();
  await expect(page.locator(".vt")).toHaveAttribute("data-vt-state", "busy");
  await expect(page.locator(".vt-content")).toHaveClass(/is-busy/);
  await expectHead(page, "login/form");
  await expect(page.locator(".vt-content")).not.toHaveClass(/is-busy/);
});

test("keeps the picture, then resumes the same reel after the socket drops", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "transport behaviour is the same at every size");
  await open(page);
  await page.getByRole("link", { name: "Sign in" }).click();
  await expectHead(page, "login/form");
  await signIn(page);
  await expectHead(page, "dashboard/home");
  const scene = await page.locator(".vt-scene").first().getAttribute("src");

  await page.evaluate(() => {
    const seen: string[] = [];
    (window as unknown as { seen: string[] }).seen = seen;
    new MutationObserver(() => seen.push(document.querySelector(".vt")!.getAttribute("data-vt-state")!))
      .observe(document.querySelector(".vt")!, { attributes: true, attributeFilter: ["data-vt-state"] });
    (window as unknown as { videotape: { dropConnection(): void } }).videotape.dropConnection();
  });
  await expect.poll(() => page.evaluate(() => (window as unknown as { seen: string[] }).seen)).toContain("offline");
  await expectHead(page, "dashboard/home");
  await expect(page.getByRole("heading", { level: 1, name: "Welcome back, Ada" })).toBeVisible();
  expect(await page.locator(".vt-scene").first().getAttribute("src")).toBe(scene);
});

test("inputs never compute below 16 px on a phone", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "phone only");
  await open(page);
  await page.getByRole("link", { name: "Sign in" }).click();
  await expectHead(page, "login/form");
  for (const label of ["Username", "Password"]) {
    const size = await page.getByLabel(label).evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
    expect(size, label).toBeGreaterThanOrEqual(16);
  }
});
