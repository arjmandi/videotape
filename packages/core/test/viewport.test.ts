import { describe, expect, it } from "vitest";
import { CANVAS, SAFE_MARGIN, stageFit, viewportClass } from "../src";

describe("viewport classes", () => {
  it.each([
    [320, "phone"], [599, "phone"], [600, "tablet"], [1023, "tablet"], [1024, "desktop"], [2560, "desktop"],
  ] as const)("width %i is %s", (w, cls) => {
    expect(viewportClass(w)).toBe(cls);
  });
});

describe("stageFit: min(cover, safe-fit)", () => {
  it("covers exactly when the aspect matches", () => {
    const f = stageFit({ w: 1920, h: 1080 }, CANVAS.desktop);
    expect(f).toMatchObject({ scale: 1, x: 0, y: 0, covers: true });
  });

  it("covers a slightly different aspect when the crop stays inside the margin", () => {
    const f = stageFit({ w: 1440, h: 900 }, CANVAS.desktop);
    expect(f.covers).toBe(true);
    const cropX = -f.x / f.w;
    expect(cropX).toBeLessThanOrEqual(SAFE_MARGIN);
  });

  it("shrinks to keep the safe area visible on a narrow phone", () => {
    const vp = { w: 390, h: 844 };
    const f = stageFit(vp, CANVAS.phone);
    expect(f.covers).toBe(false);
    const safeLeft = f.x + f.w * SAFE_MARGIN;
    const safeRight = f.x + f.w * (1 - SAFE_MARGIN);
    expect(safeLeft).toBeGreaterThanOrEqual(-1e-9);
    expect(safeRight).toBeLessThanOrEqual(vp.w + 1e-9);
    expect(f.y + f.h * SAFE_MARGIN).toBeGreaterThanOrEqual(-1e-9);
    expect(f.y + f.h * (1 - SAFE_MARGIN)).toBeLessThanOrEqual(vp.h + 1e-9);
  });

  it("keeps the safe area visible for a sweep of real viewports", () => {
    const sizes = [[375, 667], [390, 844], [430, 932], [360, 800], [768, 1024], [820, 1180], [1024, 1366], [1280, 1024], [1440, 900], [2560, 1080]];
    for (const [w, h] of sizes) {
      const f = stageFit({ w: w!, h: h! }, CANVAS[viewportClass(w!)]);
      expect(f.x + f.w * SAFE_MARGIN, `${w}x${h}`).toBeGreaterThanOrEqual(-1e-6);
      expect(f.x + f.w * (1 - SAFE_MARGIN), `${w}x${h}`).toBeLessThanOrEqual(w! + 1e-6);
      expect(f.y + f.h * SAFE_MARGIN, `${w}x${h}`).toBeGreaterThanOrEqual(-1e-6);
      expect(f.y + f.h * (1 - SAFE_MARGIN), `${w}x${h}`).toBeLessThanOrEqual(h! + 1e-6);
    }
  });
});
