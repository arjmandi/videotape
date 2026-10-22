import { describe, expect, it } from "vitest";
import { type Rect, back, button, describeArea, dusk, frame, largestFreeArea, layout, link, text } from "../src";

const hero = frame("home", { layout: "hero", components: [
  text("wordmark", "videotape", { slot: "nav.leading" }),
  link("signin", "Sign in", { slot: "nav.trailing", on: { press: back() } }),
  text("headline", "Interfaces, played.", { slot: "hero.title" }),
  text("sub", "Describe the journey.", { slot: "hero.subtitle" }),
  button("docs", "Read the docs", { slot: "hero.primary", on: { press: back() } }),
] });

const overlaps = (a: Rect, b: readonly number[]) =>
  a[0] < b[0]! + b[2]! && b[0]! < a[0] + a[2] && a[1] < b[1]! + b[3]! && b[1]! < a[1] + a[3];

describe("largestFreeArea", () => {
  it.each(["desktop", "phone", "tablet"] as const)("finds a large area clear of every content region on %s", (cls) => {
    const wf = layout(hero, cls, dusk);
    const free = largestFreeArea(wf)!;
    expect(free).toBeDefined();
    for (const r of wf.regions.filter((x) => x.z === 2)) expect(overlaps(free, r.rect), r.id).toBe(false);
    const [x, y, w, h] = free;
    expect(x).toBeGreaterThanOrEqual(wf.safe[0] - 1e-6);
    expect(y).toBeGreaterThanOrEqual(wf.safe[1] - 1e-6);
    expect(x + w).toBeLessThanOrEqual(wf.safe[0] + wf.safe[2] + 1e-6);
    expect(y + h).toBeLessThanOrEqual(wf.safe[1] + wf.safe[3] + 1e-6);
    expect(w * h).toBeGreaterThan(0.12);
  });

  it("returns the whole safe area when nothing is placed", () => {
    const wf = layout(frame("e", { layout: "blank", components: [] }), "desktop", dusk);
    expect(largestFreeArea(wf)).toEqual(wf.safe);
  });

  it("returns undefined when the safe area is full", () => {
    const wf = layout(frame("f", { layout: "blank", components: [text("t", "x", { rect: [0, 0, 1, 1] })] }), "desktop", dusk);
    expect(largestFreeArea(wf)).toBeUndefined();
  });
});

describe("describeArea", () => {
  it.each([
    [[0.06, 0.14, 0.88, 0.24], "the upper part of the frame, across its width"],
    [[0.06, 0.71, 0.88, 0.23], "the lower part of the frame, across its width"],
    [[0.12, 0.4, 0.76, 0.29], "the middle band of the frame"],
    [[0.06, 0.06, 0.3, 0.88], "the left side of the frame"],
    [[0.6, 0.65, 0.3, 0.25], "the lower right of the frame"],
  ] as Array<[Rect, string]>)("%j is %s", (rect, words) => {
    expect(describeArea(rect)).toBe(words);
  });
});
