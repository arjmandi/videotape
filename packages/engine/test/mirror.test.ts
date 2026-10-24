import { describe, expect, it } from "vitest";
import { Headless } from "../src/driver";
import { ADA, fake, play, spy } from "./harness";
import { NO_PYTHON } from "./python";

const decides = (msgs: any[]) => msgs.filter((m) => m.t === "decide");
const homeLoad = { documents: [{ record: "Home", value: { id: "home-p1", greeting: "Hello, Ada", visits: 0 } }] };

describe("the app's mirror (Q53, Q57, Q68)", () => {
  it("sends a document whole once, then by version, and keeps the app's copy current", async () => {
    const app = fake("journeys", (req) => (req.t === "load" ? homeLoad : { outcome: { type: "stay" } }));
    await app.engine.ready();
    const s = await Headless.open(app.engine, { tape: "home", user: ADA });
    await s.press("Wave");
    await s.press("Wave");
    const [first, second] = decides(app.received);
    const ref = { record: "Home", id: "home-p1" };
    expect(first.documents.home).toEqual({ ref, version: 0, value: { id: "home-p1", greeting: "Hello, Ada", visits: 0 } });
    expect(second.documents.home).toEqual({ ref, version: 0 });
    expect(app.engine.mirror!.holds(ref)).toBe(0);

  });

  it("keeps the app's copy at the confirmed value: edits, confirmed decisions, and echoes of its own (Q68)", async () => {
    const app = fake("journeys", (req, a) => {
      if (req.t === "load") return { documents: [] };
      if (req.t !== "decide") return { documents: [] };
      a.sync([{ doc: req.documents.plan!.ref, ops: [{ op: "set", path: ["title"], value: "Named" }] }], req.id);
      return req.handler === "name_plan" ? { reject: { message: "Not yet." } } : { outcome: { type: "stay" } };
    });
    await app.engine.ready();
    const s = await Headless.open(app.engine, { tape: "wizard", user: ADA });
    await s.fill({ title: "Garden" });
    await s.press("Name the plan");
    const ref = s.session.ref("Plan")!;
    const [decide] = decides(app.received);
    expect(decide.documents.plan).toEqual({ ref, version: 1, value: { title: "Garden", steps: 1 } });
    // Its change was tentative and then rolled back: the confirmed value never moved, so nothing went to the app.
    expect(app.received.slice(app.received.indexOf(decide) + 1)).toEqual([]);
    await s.fill({ steps: 3 });
    expect(app.received.at(-1)).toEqual({ t: "sync", changes: [{ doc: ref, from: 1, version: 2, ops: [{ op: "set", path: ["steps"], value: 3 }] }] });
    // A change the app makes outside any decision went through its copy: echoed with its version.
    app.sync([{ doc: ref, ops: [{ op: "set", path: ["steps"], value: 4 }] }]);
    expect(app.received.at(-1)).toEqual({ t: "sync", changes: [{ doc: ref, from: 2, version: 3, origin: "app" }] });
  });

  it("sends a decision's changes to the app's copy once they are confirmed", async () => {
    const app = fake("journeys", (req, a) => {
      if (req.t === "load") return homeLoad;
      if (req.t === "decide") a.sync([{ doc: req.documents.home!.ref, ops: [{ op: "set", path: ["visits"], value: 1 }] }], req.id);
      return { outcome: { type: "stay" } };
    });
    await app.engine.ready();
    const s = await Headless.open(app.engine, { tape: "home", user: ADA });
    await s.press("Wave");
    const ref = { record: "Home", id: "home-p1" };
    expect(app.received.at(-1)).toEqual({ t: "sync", changes: [{ doc: ref, from: 0, version: 1, ops: [{ op: "set", path: ["visits"], value: 1 }] }] });
    await s.press("Wave");
    expect(decides(app.received).at(-1).documents.home).toEqual({ ref, version: 1 });
  });

  it("asks again with the whole document when the app's copy is stale", async () => {
    let n = 0;
    const app = fake("journeys", (req) => {
      if (req.t === "load") return homeLoad;
      n += 1;
      return n === 2 ? { stale: [{ doc: { record: "Home", id: "home-p1" }, have: null }] } : { outcome: { type: "stay" } };
    });
    await app.engine.ready();
    const s = await Headless.open(app.engine, { tape: "home", user: ADA });
    await s.press("Wave");
    await s.press("Wave");
    const sent = decides(app.received).map((d) => "value" in d.documents.home);
    expect(sent).toEqual([true, false, true]);
    expect(s.error).toBeNull();
  });

  it("tells the app when a document it holds is gone, and stops when it forgets one", async () => {
    const app = fake("journeys", (req) => (req.t === "load" ? homeLoad : { outcome: { type: "stay" } }));
    await app.engine.ready();
    const s = await Headless.open(app.engine, { tape: "home", user: ADA });
    await s.press("Wave");
    s.close();
    expect(app.received.at(-1)).toEqual({ t: "sync", drop: [{ record: "Home", id: "home-p1" }] });

    const t = await Headless.open(app.engine, { tape: "home", user: ADA });
    await t.press("Wave");
    app.say({ t: "forget", docs: [{ record: "Home", id: "home-p1" }] });
    expect(app.engine.mirror!.holds({ record: "Home", id: "home-p1" })).toBeUndefined();
    await t.press("Wave");
    expect("value" in decides(app.received).at(-1).documents.home).toBe(true);
  });

  it("sends a record with secrets whole every time, with that decision's secrets, and never holds it", async () => {
    const app = fake("journeys", (req) => (req.t === "decide" ? { reject: { message: "Wrong password." } } : { documents: [] }));
    await app.engine.ready();
    const s = await Headless.open(app.engine);
    await s.fill({ name: "Ada", password: "one" });
    await s.press("Sign in");
    await s.fill({ password: "two" });
    await s.press("Sign in");
    expect(decides(app.received).map((d) => d.documents.login.value)).toEqual([{ name: "Ada", password: "one" }, { name: "Ada", password: "two" }]);
    expect(app.engine.mirror!.holds(s.session.ref("Login")!)).toBeUndefined();
  });

  it("answers a fetch with the documents it holds", async () => {
    const app = fake("journeys", (req) => (req.t === "load" ? homeLoad : { outcome: { type: "stay" } }));
    await app.engine.ready();
    await Headless.open(app.engine, { tape: "home", user: ADA });
    app.say({ t: "fetch", id: "f1", docs: [{ record: "Home", id: "home-p1" }, { record: "Home", id: "nobody" }] });
    expect(app.received.at(-1)).toEqual({ t: "fetched", id: "f1", documents: [{ doc: { record: "Home", id: "home-p1" }, version: 0, value: homeLoad.documents[0]!.value }] });
  });
});

describe.skipIf(NO_PYTHON)("the mirror with the Python app", () => {
  it("relay: after the first send, a decide names the conversation by version only", async () => {
    const p = await play("relay");
    try {
      const ada = { record: "User", id: "u1", value: { id: "u1", name: "Ada" } };
      const a = await Headless.open(p.engine, { address: "/c/c1", user: ada });
      const seen = spy(p.engine);
      for (const text of ["one", "two", "three"]) {
        await a.fill({ text });
        await a.press("Send");
      }
      const conv = decides(seen).map((d) => Object.keys(d.documents.conv).sort());
      expect(conv).toEqual([["ref", "value", "version"], ["ref", "version"], ["ref", "version"]]);
      expect(seen.filter((m) => m.t === "sync" && m.changes?.some((c: any) => "value" in c))).toEqual([]);
      expect(a.doc("Conversation").messages.map((m: any) => m.text.blocks[0].spans[0].text)).toEqual(["Ready when you are.", "one", "two", "three"]);
      expect(a.error).toBeNull();
    } finally {
      await p.stop();
    }
  }, 20_000);

  it("relay: two overlapping sends, one of which fails, leave the other and the app's copy whole (Q68)", async () => {
    const p = await play("relay");
    try {
      const ada = { record: "User", id: "u1", value: { id: "u1", name: "Ada" } };
      const grace = { record: "User", id: "u2", value: { id: "u2", name: "Grace" } };
      const a = await Headless.open(p.engine, { address: "/c/c1", user: ada });
      const b = await Headless.open(p.engine, { address: "/c/c1", user: grace });
      await a.fill({ text: "warm up" });
      await a.press("Send");                                      // the app holds the conversation from here
      const seen = spy(p.engine);
      await a.fill({ text: "fail: one" });
      await b.fill({ text: "two" });
      await Promise.all([a.press("Send"), b.press("Send")]);
      const words = (s: Headless) => s.doc("Conversation").messages.map((m: any) => m.text.blocks[0].spans[0].text);
      for (const s of [a, b]) {
        expect(words(s)).toEqual(["Ready when you are.", "warm up", "two"]);
        expect(s.doc("Conversation").messages.at(-1).pending).toBe(false);
        expect(s.tentative("Conversation")).toBe(false);
      }
      expect(a.error).not.toBeNull();
      expect(a.doc("Draft")).toEqual({ text: "fail: one" });
      expect(b.error).toBeNull();
      // The app's copy followed what was confirmed: B's changes as ops, A's never; nothing whole.
      const conv = { record: "Conversation", id: "c1" };
      const toApp = seen.filter((m) => m.t === "sync" && m.changes?.some((c: any) => c.doc.id === "c1"));
      expect(toApp.flatMap((m) => m.changes).every((c: any) => "ops" in c && !("value" in c))).toBe(true);
      await a.fill({ text: "three" });
      await a.press("Send");
      expect(decides(seen).at(-1).documents.conv).toEqual({ ref: conv, version: p.engine.mirror!.holds(conv)! - 1 });
      expect(words(b).at(-1)).toBe("three");
    } finally {
      await p.stop();
    }
  }, 20_000);

  it("journeys: work a handler leaves running lands confirmed, never tentative (Q54)", async () => {
    const p = await play("journeys");
    try {
      const a = await Headless.open(p.engine, { tape: "home", user: ADA });
      const b = await Headless.open(p.engine, { tape: "home", user: ADA });
      await a.press("Wave later");
      expect(a.doc("Home").visits).toBe(0);
      await expect.poll(() => b.doc("Home").visits).toBe(1);
      for (const s of [a, b]) expect(s.changesTo("Home").map((c) => [c.state, c.tentative, c.value.visits])).toEqual([["confirmed", false, 1]]);
    } finally {
      await p.stop();
    }
  }, 20_000);
});
