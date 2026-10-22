import { describe, expect, it } from "vitest";
import {
  type Archetype, type Component, type Frame, type Wireframe, ARCHETYPES, CANVAS, VIEWPORT_CLASSES, back, bind, button, date,
  dusk, frame, image, inferArchetype, input, isInteractive, layout, link, list, select, stageFit, text, toggle,
} from "../src";

const nav = (): Component[] => [
  link("navl", "Home", { slot: "nav.leading", on: { press: back() } }),
  link("navt", "Settings", { slot: "nav.trailing", on: { press: back() } }),
];
const go = { on: { press: back() } };

/** A frame per archetype that fills every slot. */
export const FULL: Record<Exclude<Archetype, "blank">, Frame> = {
  hero: frame("hero", { layout: "hero", components: [
    ...nav(), text("title", "Interfaces, played."), text("sub", "Describe the journey."),
    button("primary", "Start", go), link("secondary", "Later", go), image("media", "/x.png"), text("footer", "© 2026"),
  ] }),
  form: frame("form", { layout: "form", components: [
    nav()[0]!, text("title", "Sign in"), input("a", { label: "Name" }),
    select("c", { label: "Plan", options: [{ value: "p", label: "Pro" }] }),
    text("error", bind("err")), button("primary", "Go", go), link("secondary", "Forgot?", go), text("aside", "Help"),
  ] }),
  list: frame("list", { layout: "list", components: [
    ...nav(), text("title", "Inbox"), input("q", { label: "Search", type: "search" }),
    list("items", { items: bind("items"), on: { select: back() } }), button("primary", "New", go),
  ] }),
  detail: frame("detail", { layout: "detail", components: [
    ...nav(), text("title", "Report"), image("media", "/chart.svg"), text("body", "Long text"), text("meta", "Updated today"),
    button("primary", "Export", go), button("secondary", "Share", go),
  ] }),
  grid: frame("grid", { layout: "grid", components: [
    ...nav(), text("title", "Dashboard"),
    ...[1, 2, 3, 4, 5].map((i) => text(`n${i}`, String(i), { variant: "number" })), button("cellbtn", "Open", go), text("aside", "Notes"),
  ] }),
  reader: frame("reader", { layout: "reader", components: [
    nav()[0]!, text("title", "Docs"), text("body", "Body"), list("toc", { items: bind("toc"), on: { select: back() } }),
  ] }),
};

const heroNoMedia = frame("hero2", { layout: "hero", components: FULL.hero.components.filter((c) => c.id !== "media") });
const FRAMES = [...Object.values(FULL), heroNoMedia];

function overlaps(a: number[], b: number[]): boolean {
  const eps = 1e-4;
  return a[0]! < b[0]! + b[2]! - eps && b[0]! < a[0]! + a[2]! - eps && a[1]! < b[1]! + b[3]! - eps && b[1]! < a[1]! + a[3]! - eps;
}

const cases = FRAMES.flatMap((f) => VIEWPORT_CLASSES.map((cls) => [f.id, cls, f] as const));

describe.each(cases)("layout %s on %s", (_id, cls, f) => {
  const wf: Wireframe = layout(f, cls, dusk);
  const comps = wf.regions.filter((r) => r.kind !== "panel");

  it("places every component exactly once, with no diagnostics", () => {
    expect(wf.diagnostics).toEqual([]);
    expect(comps.map((r) => r.id).sort()).toEqual(f.components.map((c) => c.id).sort());
  });

  it("keeps every region inside the safe area", () => {
    for (const r of wf.regions) {
      const [x, y, w, h] = r.rect;
      expect(x, r.id).toBeGreaterThanOrEqual(0.06 - 1e-3);
      expect(y, r.id).toBeGreaterThanOrEqual(0.06 - 1e-3);
      expect(x + w, r.id).toBeLessThanOrEqual(0.94 + 1e-3);
      expect(y + h, r.id).toBeLessThanOrEqual(0.94 + 1e-3);
      expect(w * h, r.id).toBeGreaterThan(0);
    }
  });

  it("never overlaps two content regions", () => {
    for (let i = 0; i < comps.length; i++) {
      for (let j = i + 1; j < comps.length; j++) {
        expect(overlaps(comps[i]!.rect, comps[j]!.rect), `${comps[i]!.id} × ${comps[j]!.id}`).toBe(false);
      }
    }
  });

  it("keeps touch targets at 44 CSS px and inputs at 16 CSS px on the reference device", () => {
    const ref = { phone: { w: 375, h: 667 }, tablet: { w: 768, h: 1024 }, desktop: { w: 1366, h: 768 } }[cls];
    const canvas = CANVAS[cls];
    const { scale } = stageFit(ref, canvas);
    for (const r of comps) {
      if (r.kind === "panel" || !isInteractive(r.kind)) continue;
      expect(r.rect[3] * canvas.h * scale, `${r.id} height`).toBeGreaterThanOrEqual(44);
      expect(r.rect[2] * canvas.w * scale, `${r.id} width`).toBeGreaterThanOrEqual(44);
      if (r.type?.role === "control") expect(r.type.size * scale, `${r.id} font`).toBeGreaterThanOrEqual(16);
    }
  });

  it("is deterministic", () => {
    expect(layout(f, cls, dusk)).toEqual(wf);
  });

  it("lists regions in tab order: panels first, then slot order", () => {
    const firstComp = wf.regions.findIndex((r) => r.kind !== "panel");
    expect(wf.regions.slice(firstComp).every((r) => r.kind !== "panel")).toBe(true);
  });
});

describe("layout specifics", () => {
  it("collapses grid cells to 4, 2, and 1 columns", () => {
    const xs = (cls: (typeof VIEWPORT_CLASSES)[number]) =>
      new Set(layout(FULL.grid, cls, dusk).regions.filter((r) => r.id.startsWith("__cell")).map((r) => r.rect[0])).size;
    expect(xs("desktop")).toBe(4);
    expect(xs("tablet")).toBe(2);
    expect(xs("phone")).toBe(1);
  });

  it("puts form.aside beside the panel on desktop and below it elsewhere", () => {
    const at = (cls: (typeof VIEWPORT_CLASSES)[number]) => {
      const wf = layout(FULL.form, cls, dusk);
      const panel = wf.regions.find((r) => r.id === "__panel")!.rect;
      const aside = wf.regions.find((r) => r.id === "aside")!.rect;
      return aside[0] >= panel[0] + panel[2] ? "beside" : aside[1] >= panel[1] + panel[3] ? "below" : "other";
    };
    expect(at("desktop")).toBe("beside");
    expect(at("tablet")).toBe("below");
    expect(at("phone")).toBe("below");
  });

  it("puts many fields two to a row on wider screens and reports a phone overflow", () => {
    const dense = frame("dense", { layout: "form", components: [
      text("title", "Profile"), input("a", { label: "A" }), input("b", { label: "B" }), select("c", { label: "C", options: [] }),
      date("d", { label: "D" }), toggle("e", { label: "E" }), input("f", { label: "F" }), button("go", "Save", go),
    ] });
    for (const cls of ["desktop", "tablet"] as const) {
      const wf = layout(dense, cls, dusk);
      expect(wf.diagnostics, cls).toEqual([]);
      const ya = wf.regions.find((r) => r.id === "a")!.rect[1];
      expect(wf.regions.find((r) => r.id === "b")!.rect[1], cls).toBe(ya);
    }
    expect(layout(dense, "phone", dusk).diagnostics.map((d) => d.code)).toContain("overflow");
  });

  it("auto-places components without slots in declaration order", () => {
    const f = frame("f", { layout: "form", components: [text("t", "Title"), input("u", { label: "U" }), input("p", { label: "P" }), button("b", "Go", go)] });
    expect(layout(f, "desktop", dusk).regions.filter((r) => r.kind !== "panel").map((r) => [r.id, r.slot])).toEqual([
      ["t", "form.title"], ["u", "form.field.1"], ["p", "form.field.2"], ["b", "form.primary"],
    ]);
  });

  it("uses the given rects in a blank layout", () => {
    const f = frame("f", { layout: "blank", components: [text("t", "x", { rect: [0.1, 0.2, 0.3, 0.1] })] });
    expect(layout(f, "phone", dusk).regions[0]!.rect).toEqual([0.1, 0.2, 0.3, 0.1]);
  });

  it("infers the archetype when none is given (spec §6.2)", () => {
    expect(inferArchetype([{ id: "a", kind: "input" }])).toBe("form");
    expect(inferArchetype([{ id: "a", kind: "list" }])).toBe("list");
    expect(inferArchetype([1, 2, 3].map((i) => ({ id: `n${i}`, kind: "text" as const, variant: "number" })))).toBe("grid");
    expect(inferArchetype([{ id: "a", kind: "text" }])).toBe("hero");
  });

  it("draws text as bars in the conditioning SVG", () => {
    const svg = layout(FULL.hero, "desktop", dusk).svg;
    expect(svg.startsWith("<svg")).toBe(true);
    expect(svg).toContain(`fill="${dusk.palette.accent}"`); // the primary button face
    expect((svg.match(/<rect/g) ?? []).length).toBeGreaterThan(8);
  });

  it("covers every archetype in these tests", () => {
    expect(new Set([...Object.keys(FULL), "blank"])).toEqual(new Set(ARCHETYPES));
  });
});
