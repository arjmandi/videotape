import { describe, expect, it } from "vitest";
import {
  type App, type Component, type Frame, app, back, bind, button, check, frame, goto, handler, input, jump, link, list,
  stay, tape, text,
} from "../src";

const exit = () => link("out", "Out", { on: { press: back() } });

/** One tape, one frame (plus whatever is passed), entry at the first frame. */
function oneFrame(components: Component[], extra: Partial<Frame> = {}, more: Frame[] = []): App {
  return app({ entry: "t", tapes: [tape("t", { frames: [frame("f", { layout: "hero", components, ...extra }), ...more] })] });
}

const codes = (a: App, level?: "error" | "warning") =>
  check(a).filter((d) => !level || d.level === level).map((d) => d.code);

describe("check: errors", () => {
  it("duplicate ids at every level", () => {
    expect(codes(app({ entry: "t", tapes: [tape("t", { frames: [frame("f", { components: [exit()] })] }), tape("t", { frames: [frame("g", { components: [] })] })] })))
      .toContain("duplicate-id");
    expect(codes(oneFrame([exit()], {}, [frame("f", { components: [] })]))).toContain("duplicate-id");
    expect(codes(oneFrame([exit(), text("out", "x")]))).toContain("duplicate-id");
  });

  it("goto to an unknown frame", () => {
    expect(codes(oneFrame([link("x", "X", { on: { press: goto("nope") } })]), "error")).toEqual(["unknown-frame"]);
  });

  it("jump to an unknown tape, and an unknown app entry", () => {
    expect(codes(oneFrame([link("x", "X", { on: { press: jump("nope") } })]), "error")).toEqual(["unknown-tape"]);
    expect(codes(app({ entry: "nope", tapes: [tape("t", { frames: [frame("f", { components: [exit()] })] })] }), "error")).toContain("unknown-tape");
  });

  it("a slot the archetype does not define, a taken slot, and no slot left", () => {
    expect(codes(oneFrame([exit(), text("a", "A", { slot: "form.title" })]), "error")).toEqual(["unknown-slot"]);
    expect(codes(oneFrame([exit(), text("a", "A", { slot: "hero.title" }), text("b", "B", { slot: "hero.title" })]), "error")).toEqual(["slot-taken"]);
    const many = Array.from({ length: 5 }, (_, i) => text(`t${i}`, "x"));
    expect(codes(oneFrame([exit(), ...many]), "error")).toContain("no-slot-available");
  });

  it("an interactive component with no action and no handler", () => {
    expect(codes(oneFrame([exit(), button("b", "B")]), "error")).toEqual(["no-action"]);
    expect(codes(oneFrame([exit(), list("l", { items: [] })], { layout: "list" }), "error")).toEqual(["no-action"]);
  });

  it("a handler named in on.press that the frame does not define", () => {
    expect(codes(oneFrame([exit(), button("b", "B", { on: { press: "missing" } })]), "error")).toEqual(["unknown-handler"]);
  });

  it("a bind() on a secret input", () => {
    const a = oneFrame([exit(), input("p", { label: "P", type: "secret", bind: "pw" }), button("b", "Go", { on: { press: "go" } })],
      { layout: "form", on: { go: handler(() => stay(), { outcomes: [stay()] }) } });
    expect(codes(a, "error")).toEqual(["secret-bind"]);
  });

  it("an event the kind does not emit", () => {
    expect(codes(oneFrame([exit(), button("b", "B", { on: { press: back(), select: back() } })]), "error")).toEqual(["bad-event"]);
  });

  it("an unknown style and a blank component without a rect", () => {
    expect(codes(app({ entry: "t", tapes: [tape("t", { style: "neon", frames: [frame("f", { components: [exit()] })] })] }), "error"))
      .toEqual(["unknown-style"]);
    expect(codes(oneFrame([exit()], { layout: "blank" }), "error")).toEqual(["missing-rect"]);
  });

  it("a schema violation stops further checks", () => {
    const d = check(oneFrame([text("bad id", "x")]));
    expect(d.map((x) => x.code)).toEqual(["schema"]);
  });
});

describe("check: warnings", () => {
  it("unreachable frames", () => {
    expect(codes(oneFrame([exit()], {}, [frame("island", { components: [exit()] })]), "warning")).toEqual(["unreachable-frame"]);
  });

  it("handlers without outcomes", () => {
    const a = oneFrame([exit(), button("b", "B", { on: { press: "h" } })], { on: { h: handler(() => stay()) } });
    expect(codes(a, "warning")).toEqual(["handler-without-outcomes"]);
  });

  it("frames with no exit", () => {
    expect(codes(oneFrame([text("x", "dead end")]), "warning")).toEqual(["no-exit"]);
  });

  it("a stay-only handler is not an exit", () => {
    const a = oneFrame([button("b", "B", { on: { press: "h" } })], { on: { h: handler(() => stay(), { outcomes: [stay()] }) } });
    expect(codes(a, "warning")).toEqual(["no-exit"]);
  });

  it("cycles with no exit", () => {
    const a = app({ entry: "t", tapes: [tape("t", { frames: [
      frame("a", { components: [link("x", "X", { on: { press: goto("b") } })] }),
      frame("b", { components: [link("y", "Y", { on: { press: goto("a") } })] }),
    ] })] });
    expect(codes(a, "warning")).toEqual(["closed-cycle"]);
  });

  it("scene functions that read input-written paths", () => {
    const a = app({ entry: "t", tapes: [tape("t", { frames: [
      frame("f", {
        layout: "form",
        components: [input("city", { label: "City", bind: "trip.city" }), button("b", "Go", { on: { press: goto("g") } })],
      }),
      frame("g", {
        scene: (f) => `a view of ${f.city}`,
        flavour: (d) => ({ city: d.trip.city }),
        components: [exit()],
      }),
    ] })] });
    expect(codes(a, "warning")).toEqual(["scene-reads-input"]);
  });

  it("more than one primary button", () => {
    const a = oneFrame([exit(), button("a", "A", { emphasis: "primary", on: { press: back() } }), button("b", "B", { slot: "hero.primary", on: { press: back() } })]);
    expect(codes(a, "warning")).toEqual(["multiple-primary"]);
  });

  it("values collected with no handler to receive them", () => {
    expect(codes(oneFrame([exit(), input("q", { label: "Q" })], { layout: "form" }), "warning")).toEqual(["unused-values"]);
  });

  it("a bound text reading a normal path is fine", () => {
    expect(check(oneFrame([exit(), text("x", bind("a.b"))]))).toEqual([]);
  });
});
