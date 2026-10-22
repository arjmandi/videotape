import { describe, expect, it } from "vitest";
import {
  AppSchema, COMPONENT_KINDS, ComponentSchema, app, back, bind, button, frame, goto, handler, input, jsonSchemas, jump,
  link, list, select, stay, tape, text, toSpec,
} from "../src";

const sample = app({
  entry: "a",
  tapes: [
    tape("a", {
      frames: [
        frame("one", {
          layout: "form",
          scene: (f) => `mood ${f.mood}`,
          flavour: (d) => ({ mood: d.x ? "warm" : "cool" }),
          enter: () => ({ "x.y": 1 }),
          components: [
            text("t", bind("x.y"), { variant: "title" }),
            input("name", { label: "Name", bind: "form.name" }),
            select("pick", { label: "Pick", options: bind("opts") }),
            button("go", "Go", { on: { press: "submit" } }),
            link("next", "Next", { on: { press: goto("two") } }),
          ],
          on: { submit: handler(async () => jump("b", { k: 1 }), { outcomes: [jump("b"), stay()] }) },
        }),
        frame("two", { components: [link("back", "Back", { on: { press: back() } })] }),
      ],
    }),
    tape("b", { frames: [frame("only", { components: [list("l", { items: [{ id: "i", label: "I" }], on: { select: jump("a") } })] })] }),
  ],
});

describe("authoring → wire JSON", () => {
  it("serialises to JSON that the app schema accepts", () => {
    const spec = toSpec(sample);
    expect(AppSchema.safeParse(spec).success).toBe(true);
  });

  it("carries no functions, only declared outcomes and hook flags", () => {
    const json = JSON.stringify(toSpec(sample));
    expect(json).not.toContain("=>");
    const f = toSpec(sample).tapes[0]!.frames[0]!;
    expect(f.scene).toEqual({ dynamic: true });
    expect(f.flavour).toBe(true);
    expect(f.enter).toBe(true);
    expect(f.on).toEqual({ submit: { outcomes: [{ type: "jump", tape: "b" }, { type: "stay" }] } });
  });

  it("writes a bound text as `bind`, as in spec §5.4", () => {
    const t = toSpec(sample).tapes[0]!.frames[0]!.components[0]!;
    expect(t).toMatchObject({ id: "t", kind: "text", bind: "x.y" });
    expect(t).not.toHaveProperty("value");
  });

  it("fills in tape defaults: style dusk, entry = first frame", () => {
    const t = toSpec(sample).tapes[0]!;
    expect(t.style).toBe("dusk");
    expect(t.entry).toBe("one");
  });

  it("includes the built-in style packs", () => {
    expect(toSpec(sample).styles.map((s) => s.id)).toContain("dusk");
  });

  it("keeps the schema's component kinds in step with the model", () => {
    expect(ComponentSchema.options.map((o) => o.shape.kind.value).sort()).toEqual([...COMPONENT_KINDS].sort());
  });

  it("rejects ids that are not identifiers and paths that are not dotted names", () => {
    const bad = toSpec(app({ entry: "a", tapes: [tape("a", { frames: [frame("1x", { components: [] })] })] }));
    expect(AppSchema.safeParse(bad).success).toBe(false);
    const badPath = toSpec(app({ entry: "a", tapes: [tape("a", { frames: [frame("f", { components: [text("t", bind("a..b"))] })] })] }));
    expect(AppSchema.safeParse(badPath).success).toBe(false);
  });

  it("exports JSON Schema for the app and both VTP directions", () => {
    const s = jsonSchemas();
    expect(Object.keys(s)).toEqual(["app", "vtp-client", "vtp-server"]);
    expect(JSON.stringify(s.app)).toContain("\"components\"");
    expect(JSON.stringify(s["vtp-client"])).toContain("\"hello\"");
  });
});
