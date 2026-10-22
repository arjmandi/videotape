import { describe, expect, it } from "vitest";
import { app, back, buildGraph, button, frame, goto, handler, jump, link, reachable, stay, tape, toMermaid, toSpec } from "../src";

const sample = app({
  entry: "a",
  tapes: [
    tape("a", {
      entry: "start",
      frames: [
        frame("start", {
          components: [
            link("next", "Next", { on: { press: goto("second") } }),
            button("go", "Go", { on: { press: "submit" } }),
          ],
          on: { submit: handler(() => stay(), { outcomes: [jump("b", { from: "a" }), stay()] }) },
        }),
        frame("second", { components: [link("back", "Back", { on: { press: back() } })] }),
        frame("orphan", { components: [link("back", "Back", { on: { press: back() } })] }),
      ],
    }),
    tape("b", { frames: [frame("home", { components: [link("ret", "Return", { on: { press: back() } })] })] }),
  ],
});

describe("graph", () => {
  const g = buildGraph(toSpec(sample));

  it("has the tape entry frame as its entry", () => {
    expect(g.entry).toBe("a/start");
    expect(g.nodes).toEqual(["a/start", "a/second", "a/orphan", "b/home"]);
  });

  it("extracts static edges and declared handler outcomes", () => {
    expect(g.edges).toEqual([
      { from: "a/start", component: "next", event: "press", kind: "goto", to: "a/second" },
      { from: "a/start", component: "go", event: "press", handler: "submit", kind: "jump", to: "b/home", data: { from: "a" } },
      { from: "a/start", component: "go", event: "press", handler: "submit", kind: "stay" },
      { from: "a/second", component: "back", event: "press", kind: "back" },
      { from: "a/orphan", component: "back", event: "press", kind: "back" },
      { from: "b/home", component: "ret", event: "press", kind: "back" },
    ]);
  });

  it("finds reachable frames from the entry", () => {
    expect([...reachable(g)].sort()).toEqual(["a/second", "a/start", "b/home"]);
  });

  it("renders stable Mermaid", () => {
    const m = toMermaid(g);
    expect(m).toMatchInlineSnapshot(`
      "flowchart LR
        a_start["a/start"]
        a_second["a/second"]
        a_orphan["a/orphan"]
        b_home["b/home"]
        back(("back"))
        a_start -->|"next·press"| a_second
        a_start -->|"go·press ⇒ submit"| b_home
        a_start -->|"go·press ⇒ submit"| a_start
        a_second -.->|"back·press"| back
        a_orphan -.->|"back·press"| back
        b_home -.->|"ret·press"| back
        style a_start stroke-width:3px
      "
    `);
  });
});
