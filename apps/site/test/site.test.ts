import { describe, expect, it } from "vitest";
import {
  AppSchema, CANVAS, VIEWPORT_CLASSES, buildGraph, check, isInteractive, layout, reachable, stageFit, styleById, toSpec,
} from "@videotape/core";
import demo from "../tapes";

describe("the demo app", () => {
  it("passes videotape check with no errors and no warnings (S6, M0 exit)", () => {
    expect(check(demo)).toEqual([]);
  });

  it("serialises to a valid wire spec", () => {
    expect(AppSchema.safeParse(toSpec(demo)).success).toBe(true);
  });

  it("reaches every frame from the landing page", () => {
    const g = buildGraph(toSpec(demo));
    expect(reachable(g).size).toBe(g.nodes.length);
    expect(g.nodes).toEqual([
      "landing/home", "docs/read", "login/form", "dashboard/home", "report/view", "settings/main", "reset/main",
    ]);
  });
});

const frames = demo.tapes.flatMap((t) => t.frames.map((f) => ({ t, f })));
const cases = frames.flatMap(({ t, f }) => VIEWPORT_CLASSES.map((cls) => [`${t.id}/${f.id}`, cls, t, f] as const));

describe.each(cases)("wireframe %s on %s", (name, cls, t, f) => {
  const wf = layout(f, cls, styleById(t.style ?? "dusk")!);

  it("matches the snapshot (M0 exit)", async () => {
    const base = `__snapshots__/wireframes/${name.replace("/", ".")}.${cls}`;
    const { svg, ...json } = wf;
    await expect(JSON.stringify(json, null, 2) + "\n").toMatchFileSnapshot(`${base}.json`);
    await expect(svg + "\n").toMatchFileSnapshot(`${base}.svg`);
  });

  it("has no layout diagnostics and keeps touch targets on the reference device", () => {
    expect(wf.diagnostics).toEqual([]);
    const ref = { phone: { w: 375, h: 667 }, tablet: { w: 768, h: 1024 }, desktop: { w: 1366, h: 768 } }[cls];
    const { scale } = stageFit(ref, CANVAS[cls]);
    for (const r of wf.regions) {
      if (r.kind === "panel" || !isInteractive(r.kind)) continue;
      expect(r.rect[3] * CANVAS[cls].h * scale, r.id).toBeGreaterThanOrEqual(44);
    }
  });
});
