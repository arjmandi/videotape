import { describe, expect, it } from "vitest";
import {
  type ServerMessage, app, back, bind, button, frame, goto, handler, input, jump, link, stay, tape, text, toggle,
} from "@videotape/core";
import demo from "../../../apps/site/tapes";
import { services } from "../../../apps/site/services";
import { harness, settle } from "./harness";

const types = (ms: ServerMessage[]) => ms.map((m) => m.t);
type Patch = Extract<ServerMessage, { t: "patch" }>;
const patches = (ms: ServerMessage[]) => ms.filter((m): m is Patch => m.t === "patch");
const contentOf = (h: ReturnType<typeof harness>, id: string) => h.render().content.find((c) => c.id === id);

describe("session", () => {
  it("answers hello with welcome, then a render at the entry", async () => {
    const h = harness(demo, services);
    await h.hello();
    const [welcome, render] = h.take();
    expect(welcome).toMatchObject({ t: "welcome", viewportClass: "desktop", canvas: { w: 1920, h: 1080 }, style: { id: "dusk" } });
    expect(render).toMatchObject({ t: "render", seq: 1, head: { tape: "landing", frame: "home" }, fallback: false });
  });

  it.each([[599, "phone"], [600, "tablet"], [1023, "tablet"], [1024, "desktop"]] as const)("snaps width %i to %s", async (w, cls) => {
    const h = harness(demo, services);
    await h.hello({ w, h: 800 });
    expect(h.take()[0]).toMatchObject({ viewportClass: cls });
  });

  it("requires hello before anything else", async () => {
    const h = harness(demo, services);
    await h.send({ t: "resize", viewport: { w: 400, h: 800, dpr: 1 } });
    expect(h.take()).toEqual([{ t: "error", code: "no_session", message: "send hello first", recoverable: true }]);
  });

  it("answers ping with pong", async () => {
    const h = harness(demo, services);
    await h.send({ t: "ping" });
    expect(types(h.take())).toEqual(["pong"]);
  });

  it("resumes a reel by token with its head and data", async () => {
    const h = harness(demo, services);
    await h.hello();
    const token = (h.take()[0] as { token: string }).token;
    await h.press("signin");
    await h.press("submit", { username: "ada", password: "lovelace" });
    expect(h.render().head).toEqual({ tape: "dashboard", frame: "home" });

    const h2 = h.reconnect();
    await h2.hello({ w: 1440, h: 900 }, token);
    const [welcome, render] = h2.take();
    expect(welcome).toMatchObject({ t: "welcome", token });
    expect(render).toMatchObject({ t: "render", head: { tape: "dashboard", frame: "home" } });
    expect(h2.render().content.find((c) => c.id === "hello")?.value).toBe("Welcome back, Ada");
  });

  it("starts fresh on an unknown token", async () => {
    const h = harness(demo, services);
    await h.hello({ w: 1440, h: 900 }, "not-a-token");
    expect(h.render().head).toEqual({ tape: "landing", frame: "home" });
  });

  it("sends a new render when the viewport class changes, and nothing otherwise", async () => {
    const h = harness(demo, services);
    await h.hello();
    h.take();
    await h.send({ t: "resize", viewport: { w: 1300, h: 800, dpr: 1 } });
    expect(h.take()).toEqual([]);
    await h.send({ t: "resize", viewport: { w: 390, h: 844, dpr: 3 } });
    const r = h.take().find((m) => m.t === "render");
    expect(r).toMatchObject({ head: { tape: "landing", frame: "home" } });
    expect(h.render().regions.length).toBeGreaterThan(0);
  });
});

describe("event validation", () => {
  async function onLogin() {
    const h = harness(demo, services);
    await h.hello();
    await h.press("signin");
    h.take();
    return h;
  }
  const headAfter = async (h: ReturnType<typeof harness>, msg: Record<string, unknown>) => {
    await h.send({ t: "event", seq: h.nextSeq(), render: h.render().seq, ...msg });
    return h.render().head;
  };
  const login = { tape: "login", frame: "form" };

  it("drops an unknown component", async () => {
    const h = await onLogin();
    expect(await headAfter(h, { component: "ghost", type: "press" })).toEqual(login);
    expect(h.log.lines.some((l) => l.msg === "dropped event: unknown component")).toBe(true);
  });

  it("drops an event the kind does not emit", async () => {
    const h = await onLogin();
    expect(await headAfter(h, { component: "forgot", type: "change" })).toEqual(login);
  });

  it("drops an event the frame does not handle", async () => {
    const h = await onLogin();
    expect(await headAfter(h, { component: "username", type: "change", value: "x" })).toEqual(login);
    expect(h.log.lines.some((l) => l.msg === "dropped event: not handled by this frame")).toBe(true);
  });

  it("drops a wrong value type and values naming a non-value component", async () => {
    const h = await onLogin();
    expect(await headAfter(h, { component: "submit", type: "press", values: { username: 7, password: "lovelace" } })).toEqual(login);
    expect(await headAfter(h, { component: "submit", type: "press", values: { submit: "x" } })).toEqual(login);
  });

  it("drops a value over 4 KB at the schema", async () => {
    const h = await onLogin();
    await h.send({ t: "event", seq: h.nextSeq(), render: h.render().seq, component: "submit", type: "press", values: { username: "x".repeat(5000) } });
    expect(h.take()).toContainEqual(expect.objectContaining({ t: "error", code: "bad_message" }));
    expect(h.render().head).toEqual(login);
  });

  it("drops an event made against an older render", async () => {
    const h = await onLogin();
    const stale = h.render().seq - 1;
    await h.send({ t: "event", seq: h.nextSeq(), render: stale, component: "forgot", type: "press" });
    expect(h.render().head).toEqual(login);
    expect(h.log.lines.some((l) => l.msg === "dropped event: stale render")).toBe(true);
  });

  it("drops a replayed seq", async () => {
    const h = await onLogin();
    const seq = h.nextSeq();
    await h.send({ t: "event", seq, render: h.render().seq, component: "submit", type: "press", values: { username: "x", password: "y" } });
    h.take();
    await h.send({ t: "event", seq, render: h.render().seq, component: "forgot", type: "press" });
    expect(h.render().head).toEqual(login);
  });
});

describe("actions", () => {
  const nav = app({
    entry: "a",
    tapes: [
      tape("a", { frames: [
        frame("one", { components: [link("next", "Next", { on: { press: goto("two") } }), link("out", "Out", { on: { press: jump("b", { "b.from": "a" }) } })] }),
        frame("two", { components: [link("back", "Back", { on: { press: back() } }), link("prev", "Prev", { on: { press: goto("one") } })] }),
      ] }),
      tape("b", { frames: [frame("home", { components: [text("from", bind("b.from")), link("back", "Back", { on: { press: back() } })] })] }),
    ],
  });

  it("goto moves within the tape without touching history", async () => {
    const h = harness(nav);
    await h.hello();
    await h.press("next");
    expect(h.render().head).toEqual({ tape: "a", frame: "two" });
    h.take();
    await h.press("back"); // empty history: stays
    expect(types(h.take())).toEqual(["patch"]);
    expect(h.render().head).toEqual({ tape: "a", frame: "two" });
  });

  it("jump pushes history and merges data; back pops", async () => {
    const h = harness(nav);
    await h.hello();
    await h.press("out");
    expect(h.render().head).toEqual({ tape: "b", frame: "home" });
    expect(contentOf(h, "from")?.value).toBe("a");
    await h.press("back");
    expect(h.render().head).toEqual({ tape: "a", frame: "one" });
  });

  it("sends a crossfade cut before the next render", async () => {
    const h = harness(nav);
    await h.hello();
    const first = h.render().key;
    h.take();
    await h.press("next");
    const [cut, render] = h.take();
    expect(cut).toMatchObject({ t: "cut", kind: "crossfade", from: first, durationMs: 400 });
    expect(cut).not.toHaveProperty("url");
    expect(render).toMatchObject({ t: "render" });
    expect((cut as { to: string }).to).toBe((render as { key: string }).key);
  });

  it("stay sends a patch with only the changed components", async () => {
    const h = harness(demo, services);
    await h.hello();
    await h.press("signin");
    h.take();
    await h.press("submit", { username: "ada", password: "wrong" });
    const [p] = patches(h.take());
    expect(p!.content).toEqual([{ id: "error", value: "Wrong credentials" }]);
    expect(h.render().head).toEqual({ tape: "login", frame: "form" });
  });

  it("lists edges with resolved targets, including the concrete back target", async () => {
    const h = harness(demo, services);
    await h.hello();
    await h.press("signin");
    const edges = h.render().edges;
    expect(edges).toContainEqual({ component: "home", event: "press", kind: "back", to: { tape: "landing", frame: "home" } });
    expect(edges).toContainEqual({ component: "submit", event: "press", kind: "jump", handler: "submit", to: { tape: "dashboard", frame: "home" } });
    expect(edges).toContainEqual({ component: "submit", event: "press", kind: "stay", handler: "submit" });
  });
});

describe("handlers", () => {
  const seen: Array<Record<string, unknown>> = [];
  const fixture = app({
    entry: "t",
    tapes: [
      tape("t", { frames: [frame("f", {
        layout: "form",
        components: [
          input("name", { label: "Name", bind: "profile.name" }),
          input("pin", { label: "PIN", type: "secret" }),
          toggle("news", { label: "News", commit: "change", bind: "profile.news" }),
          text("shown", bind("profile.name")),
          button("save", "Save", { on: { press: "save" } }),
          link("boom", "Boom", { slot: "form.secondary", on: { press: "boom" } }),
        ],
        on: {
          save: handler(({ values }) => {
            seen.push(values);
            return values.pin === "1234" ? jump("u") : stay();
          }, { outcomes: [jump("u"), stay()] }),
          boom: handler(() => { throw new Error("kaboom"); }, { outcomes: [stay()] }),
        },
      })] }),
      tape("u", { frames: [frame("g", { components: [text("x", "done"), link("back", "Back", { on: { press: back() } })] })] }),
    ],
  });

  it("receives committed values and writes bound ones to the store", async () => {
    const h = harness(fixture);
    await h.hello();
    await h.press("save", { name: "Ada", pin: "0000" });
    expect(seen.at(-1)).toEqual({ name: "Ada", pin: "0000" });
    const [p] = patches(h.take());
    expect(p!.content).toContainEqual({ id: "shown", value: "Ada" });
    expect(p!.content).toContainEqual({ id: "name", value: "Ada" });
  });

  it("commits a bound value with commit: change and no handler", async () => {
    const h = harness(fixture);
    await h.hello();
    h.take();
    await h.send({ t: "event", seq: h.nextSeq(), render: h.render().seq, component: "news", type: "change", value: true });
    const [p] = patches(h.take());
    expect(p!.content).toEqual([{ id: "news", value: true }]);
  });

  it("never stores, logs, renders, or patches back a secret", async () => {
    const h = harness(fixture);
    await h.hello();
    await h.press("save", { name: "Ada", pin: "1234" });
    expect(h.render().head).toEqual({ tape: "u", frame: "g" });
    await h.press("back");
    const everything = JSON.stringify(h.sent) + JSON.stringify(h.log.lines);
    expect(everything).not.toContain("1234");
    expect(h.render().content.find((c) => c.id === "pin")).not.toHaveProperty("value");
  });

  it("turns a throwing handler into a recoverable error and keeps the head", async () => {
    const h = harness(fixture);
    await h.hello();
    h.take();
    await h.press("boom");
    const out = h.take();
    expect(out).toContainEqual(expect.objectContaining({ t: "error", code: "handler_failed", recoverable: true }));
    expect(types(out)).toContain("patch");
    expect(JSON.stringify(out)).not.toContain("kaboom");
  });

  it("allows but logs an outcome the handler did not declare", async () => {
    const loose = app({ entry: "t", tapes: [
      tape("t", { frames: [frame("f", { components: [button("b", "B", { on: { press: "h" } })], on: { h: handler(() => jump("u"), { outcomes: [stay()] }) } })] }),
      tape("u", { frames: [frame("g", { components: [link("back", "Back", { on: { press: back() } })] })] }),
    ] });
    const h = harness(loose);
    await h.hello();
    await h.press("b");
    expect(h.render().head).toEqual({ tape: "u", frame: "g" });
    expect(h.log.lines.some((l) => l.msg === "handler returned an undeclared outcome")).toBe(true);
  });
});

describe("enter hooks", () => {
  it("run before the first render and on arrival by jump and back", async () => {
    let calls = 0;
    const hooked = app({ entry: "a", tapes: [
      tape("a", { frames: [frame("one", {
        enter: () => ({ "visits.a": ++calls }),
        components: [text("v", bind("visits.a")), link("go", "Go", { on: { press: jump("b") } })],
      })] }),
      tape("b", { frames: [frame("two", { components: [link("back", "Back", { on: { press: back() } })] })] }),
    ] });
    const h = harness(hooked);
    await h.hello();
    expect(contentOf(h, "v")?.value).toBe("1");
    await h.press("go");
    await h.press("back");
    expect(contentOf(h, "v")?.value).toBe("2");
  });

  it("load the demo's dashboard and report data", async () => {
    const h = harness(demo, services);
    await h.hello();
    await h.press("signin");
    await h.press("submit", { username: "ada", password: "lovelace" });
    expect(contentOf(h, "views")?.value).toBe("12,480 views");
    await h.press("report");
    expect(contentOf(h, "chart")).toMatchObject({ src: "/app/chart.svg", alt: "Views per day, last 30 days" });
  });
});

describe("render", () => {
  it("lists content in tab order with resolved values and no handler code", async () => {
    const h = harness(demo, services);
    await h.hello();
    await h.press("docs");
    const r = h.render();
    expect(r.content.map((c) => c.id)).toEqual(["home", "title", "body", "toc"]);
    expect(r.content.find((c) => c.id === "toc")?.items?.[0]).toEqual({ id: "intro", label: "What Videotape is" });
    expect(JSON.stringify(r)).not.toContain("=>");
  });

  it("uses list select values as values.item", async () => {
    const h = harness(demo, services);
    await h.hello();
    await h.press("docs");
    h.take();
    await h.select("toc", "layout");
    const [p] = patches(h.take());
    expect(p!.content).toContainEqual({ id: "title", value: "Layout owns space" });
  });

  it("rejects a list item that is not in the list", async () => {
    const h = harness(demo, services);
    await h.hello();
    await h.press("docs");
    h.take();
    await h.select("toc", "../../etc/passwd");
    expect(h.take()).toEqual([]);
  });

  it("serves the same asset URL for the same frame across sessions", async () => {
    const h = harness(demo, services);
    await h.hello();
    const h2 = harness(demo, services, { cache: h.engine.cache });
    await h2.hello();
    expect(h2.render().layers).toEqual(h.render().layers);
  });

  it("sends a prefetch for every outgoing edge's target scene", async () => {
    const h = harness(demo, services);
    await h.hello();
    await settle(200);
    const pf = h.sent.find((m) => m.t === "prefetch") as Extract<ServerMessage, { t: "prefetch" }>;
    expect(pf.assets.map((a) => a.forEdge).sort()).toEqual(["docs:press", "signin:press"]);
    expect(pf.assets.every((a) => a.url.startsWith("/a/"))).toBe(true);
  });
});
