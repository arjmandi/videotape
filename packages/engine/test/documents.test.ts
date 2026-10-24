import { afterEach, describe, expect, it, vi } from "vitest";
import { type DocChange, DocumentStore } from "../src/documents";
import { memoryLogger } from "../src/log";
import type { Op } from "../src/protocol";
import { KEY, Records } from "../src/records";
import { Headless } from "../src/driver";
import { ADA, fake, play } from "./harness";
import { intent, rawIntent } from "./fixtures";
import { NO_PYTHON } from "./python";

const relay = new Records(intent("relay"));
const user = { id: "u1", name: "Ada" };
const text = (s: string) => ({ blocks: [{ kind: "paragraph", spans: [{ text: s }] }] });
const message = (s: string, extra = {}) => ({ author: user, text: text(s), sent_at: null, pending: false, ...extra });
const conversation = () => ({ id: "c1", title: "Launch", typing: null, messages: [message("first")] });

function store() {
  const log = memoryLogger();
  const docs = new DocumentStore(relay, log);
  const changes: DocChange[] = [];
  docs.onChange((c) => changes.push({ ...c, doc: { ...c.doc } }));
  return { docs, log, changes };
}

const texts = (value: any) => value.messages.map((m: any) => m.text.blocks[0].spans[0].text);
const insert = (key: string, s: string, extra = {}): Op => ({ op: "insert", path: ["messages"], key, value: message(s, extra), at: "end" });

describe("the document store", () => {
  it("holds a document with an Id once, shared by every holder, until the last lets go", () => {
    const { docs } = store();
    const a = docs.load("Conversation", conversation(), "s1:1");
    const b = docs.load("Conversation", conversation(), "s2:1");
    expect(a).toEqual({ record: "Conversation", id: "c1" });
    expect(b).toEqual(a);
    expect(docs.size).toBe(1);
    docs.release("s1:1");
    expect(docs.get(a)).toBeDefined();
    docs.release("s2:1");
    expect(docs.get(a)).toBeUndefined();
  });

  it("makes documents without an Id, and edited ones, the holder's own", () => {
    const { docs } = store();
    const draft = docs.load("Draft", { text: "" }, "s1:1");
    expect(draft).toEqual({ record: "Draft", local: "d1" });
    const edited = docs.load("Conversation", conversation(), "s1:1", true);
    expect("local" in edited).toBe(true);
    const nullId = docs.load("Conversation", { ...conversation(), id: null }, "s1:1");
    expect("local" in nullId).toBe(true);
    expect(docs.size).toBe(3);
  });

  it("shows a decision's changes at once, and folds them in when it returns", () => {
    const { docs, changes } = store();
    const ref = docs.load("Conversation", conversation(), "s1:1");
    docs.tentative("r1", ref, [insert("~a.1", "second", { pending: true })]);
    expect(texts(docs.read(ref))).toEqual(["first", "second"]);
    expect(docs.isTentative(ref)).toBe(true);
    docs.tentative("r1", ref, [{ op: "set", path: ["messages", { key: "~a.1" }, "pending"], value: false }]);
    docs.confirm("r1");
    expect(docs.isTentative(ref)).toBe(false);
    expect(docs.get(ref)!.confirmed).toEqual(docs.get(ref)!.value);
    expect((docs.read(ref) as any).messages[1].pending).toBe(false);
    expect(changes.map((c) => [c.state, c.decision])).toEqual([["tentative", "r1"], ["tentative", "r1"], ["confirmed", "r1"]]);
  });

  it("takes a failed decision's changes back, and keeps another decision's", () => {
    const { docs, changes } = store();
    const ref = docs.load("Conversation", conversation(), "s1:1");
    docs.tentative("r1", ref, [insert("~a.1", "mine")]);
    docs.tentative("r2", ref, [insert("~b.1", "theirs")]);
    docs.tentative("r1", ref, [{ op: "set", path: ["title"], value: "Renamed" }]);
    expect(texts(docs.read(ref))).toEqual(["first", "mine", "theirs"]);
    docs.rollback("r1");
    expect(texts(docs.read(ref))).toEqual(["first", "theirs"]);
    expect((docs.read(ref) as any).title).toBe("Launch");
    expect(docs.isTentative(ref)).toBe(true);
    docs.confirm("r2");
    expect(texts(docs.get(ref)!.confirmed)).toEqual(["first", "theirs"]);
    expect(changes.map((c) => c.state)).toEqual(["tentative", "tentative", "tentative", "rolledback", "confirmed"]);
  });

  it("re-applies open decisions on top of a change confirmed meanwhile", () => {
    const { docs } = store();
    const ref = docs.load("Conversation", conversation(), "s1:1");
    docs.tentative("r1", ref, [insert("~a.1", "pending")]);
    docs.apply(ref, [insert("~app.1", "delivered")]);
    expect(texts(docs.read(ref))).toEqual(["first", "delivered", "pending"]);
    expect(texts(docs.get(ref)!.confirmed)).toEqual(["first", "delivered"]);
    docs.load("Conversation", { ...conversation(), title: "Reloaded" }, "s2:1");
    expect((docs.read(ref) as any).title).toBe("Reloaded");
    expect(texts(docs.read(ref))).toEqual(["first", "pending"]);
  });

  it("keys the items a decision adds the same way every time it is applied again", () => {
    const crm = new Records(intent("crm"));
    const docs = new DocumentStore(crm, memoryLogger());
    const ref = docs.load("Pipeline", { deals: [] }, "s1:1", true);
    const deal = { id: null, name: "D", company: { id: "co1", name: "Acme" }, amount: { amount: "1", currency: "EUR" }, stage: "lead", owner: { id: "u1", name: "Ada" } };
    docs.tentative("r1", ref, [{ op: "insert", path: ["deals"], key: "~a.1", value: deal }]);
    const before = JSON.stringify(docs.get(ref)!.value);
    docs.edit(ref, [{ op: "set", path: ["deals"], value: [] }]);
    docs.apply(ref, []);
    expect(JSON.stringify(docs.get(ref)!.value)).toBe(before);
  });

  it("finds items by key or by Id, and refuses what does not fit the record", () => {
    const { docs, log } = store();
    const ref = docs.load("Conversation", conversation(), "s1:1");
    const key = (docs.get(ref)!.value as any).messages[0][KEY];
    expect(docs.apply(ref, [{ op: "replace", path: ["messages"], key, value: message("edited") }])).toHaveLength(1);
    expect(texts(docs.read(ref))).toEqual(["edited"]);
    expect(docs.apply(ref, [{ op: "set", path: ["title"], value: 5 }])).toEqual([]);
    expect(docs.apply(ref, [{ op: "set", path: ["nope"], value: 1 }])).toEqual([]);
    expect(docs.apply(ref, [{ op: "remove", path: ["messages"], key: "missing" }])).toEqual([]);
    expect(log.lines.filter((l) => l.msg === "an op was refused").map((l) => l.fields?.reason)).toEqual([
      "title: / must be string", "Conversation has no nope", "no item missing in messages",
    ]);
    expect(docs.apply(ref, [{ op: "remove", path: ["messages"], key }])).toHaveLength(1);
    expect(texts(docs.read(ref))).toEqual([]);
  });
});

describe("documents across sessions", () => {
  it("fans the app's own changes out to every session that shows the document", async () => {
    const app = fake("journeys", (req) => {
      if (req.t === "load") return { documents: [{ record: "Inbox", value: { id: "inbox-p1", items: [{ id: "i1", title: "First" }] } }] };
      return { outcome: { type: "stay" } };
    });
    await app.engine.ready();
    const a = await Headless.open(app.engine, { tape: "inbox", user: ADA });
    const b = await Headless.open(app.engine, { tape: "inbox", user: ADA });
    const elsewhere = await Headless.open(app.engine, { tape: "home", user: ADA });
    app.sync([{ doc: { record: "Inbox", id: "inbox-p1" }, ops: [{ op: "insert", path: ["items"], key: "i2", value: { id: "i2", title: "Second" } }] }]);
    for (const c of [a, b]) {
      expect(c.changes.map(({ at: _, ...rest }) => rest)).toEqual([
        { record: "Inbox", state: "confirmed", tentative: false, value: { id: "inbox-p1", items: [{ id: "i1", title: "First" }, { id: "i2", title: "Second" }] } },
      ]);
    }
    expect(elsewhere.changes).toEqual([]);
    app.sync([{ doc: { record: "Inbox", id: "nobody" }, ops: [{ op: "set", path: ["items"], value: [] }] }]);
    expect(a.changes).toHaveLength(1);
  });
});

describe.skipIf(NO_PYTHON)("documents with the Python app", () => {
  it("journeys: a Reject rolls back what the handler changed, in every session showing it", async () => {
    const p = await play("journeys");
    try {
      const a = await Headless.open(p.engine, { tape: "home", user: ADA });
      const b = await Headless.open(p.engine, { tape: "home", user: ADA });
      await a.press("Wave");
      await a.press("Wave too much");
      expect(a.view.status.error).toBe("Too much waving.");
      for (const c of [a, b]) {
        expect(c.changes.map((x) => [x.state, x.value.visits])).toEqual([["tentative", 1], ["confirmed", 1], ["tentative", 11], ["rolledback", 1]]);
        expect(c.doc("Home").visits).toBe(1);
      }
    } finally {
      await p.stop();
    }
  }, 20_000);
});

describe("on_change, paced (Q72, Q74)", () => {
  afterEach(() => vi.useRealTimers());

  /** The journeys app with a fake service: save_plan answers when `release` says, if it says to wait. */
  async function wizard(opts: { intent?: unknown; hold?: boolean } = {}) {
    const releases: Array<() => void> = [];
    const app = fake("journeys", (req) => {
      if (req.t === "load") return { documents: [] };
      if (req.t === "decide" && req.handler === "save_plan" && opts.hold) {
        return new Promise((resolve) => releases.push(() => resolve({ outcome: { type: "stay" } })));
      }
      return req.t === "decide" && req.handler === "name_plan" ? { outcome: { type: "goto", frame: "steps" } } : { outcome: { type: "stay" } };
    }, opts.intent ? { intent: opts.intent } : {});
    await app.engine.ready();
    const s = await Headless.open(app.engine, { tape: "wizard", user: ADA });
    const saves = () => (app.requests.filter((r) => r.t === "decide" && r.handler === "save_plan") as Array<{ documents: Record<string, { value?: any }> }>)
      .map((r) => r.documents.plan!.value?.title ?? "(by version)");
    const decided = () => app.requests.filter((r) => r.t === "decide").map((r) => (r as { handler: string }).handler);
    return { app, s, saves, decided, release: () => releases.shift()?.() };
  }

  it("waits for a pause in changes, 300 ms by default", async () => {
    vi.useFakeTimers();
    const { s, decided } = await wizard();
    await s.fill({ title: "G" });
    await vi.advanceTimersByTimeAsync(200);
    await s.fill({ title: "Ga" });
    await vi.advanceTimersByTimeAsync(299);
    expect(decided()).toEqual([]);
    await vi.advanceTimersByTimeAsync(1);
    await s.settled();
    expect(decided()).toEqual(["save_plan"]);
    expect(s.doc("Plan").title).toBe("Ga");
  });

  it("waits as long as the field's pause= says", async () => {
    vi.useFakeTimers();
    const intent = structuredClone(rawIntent("journeys")) as any;
    const name = intent.tapes.find((t: any) => t.id === "wizard").frames[0];
    name.components.find((c: any) => c.field === "Plan.title").pause = 0.05;
    const { s, decided } = await wizard({ intent });
    await s.fill({ title: "Garden" });
    await vi.advanceTimersByTimeAsync(50);
    await s.settled();
    expect(decided()).toEqual(["save_plan"]);
  });

  it("runs at once on blur, and not again when the pause ends", async () => {
    vi.useFakeTimers();
    const { s, decided } = await wizard();
    await s.fill({ title: "Garden" });
    await s.blur("title");
    expect(decided()).toEqual(["save_plan"]);
    await vi.advanceTimersByTimeAsync(1000);
    await s.settled();
    expect(decided()).toEqual(["save_plan"]);
    await s.blur("title");                                          // nothing changed since
    expect(decided()).toEqual(["save_plan"]);
  });

  it("runs before a submit, so the submit sees its result", async () => {
    vi.useFakeTimers();
    const { s, decided } = await wizard();
    await s.fill({ title: "Garden" });
    await s.press("Name the plan");
    expect(decided()).toEqual(["save_plan", "name_plan"]);
    expect(s.place).toBe("wizard/steps");
    await vi.advanceTimersByTimeAsync(1000);
    await s.settled();
    expect(decided()).toEqual(["save_plan", "name_plan"]);          // the pause timer was the frame's, and it is gone
  });

  it("lets the newest change replace a run that has not started, and follows a run in flight with one more", async () => {
    vi.useFakeTimers();
    const { app, s, decided, release } = await wizard({ hold: true });
    await s.fill({ title: "a" });
    void s.blur("title");                                           // run 1 starts, and waits on the app
    await vi.advanceTimersByTimeAsync(0);
    await s.fill({ title: "ab" });
    void s.blur("title");                                           // run 2 waits for run 1
    await s.fill({ title: "abc" });
    void s.blur("title");                                           // run 2 is waiting: it will read the latest
    await s.fill({ title: "abcd" });
    await vi.advanceTimersByTimeAsync(300);                         // the pause ends: still the one waiting run
    expect(decided()).toEqual(["save_plan"]);
    release();
    await vi.advanceTimersByTimeAsync(0);
    release();
    await s.settled();
    expect(decided()).toEqual(["save_plan", "save_plan"]);
    const values = (app.requests.filter((r) => r.t === "decide") as Array<{ documents: Record<string, { ref: unknown }> }>).map((r) => r.documents.plan);
    expect(values.length).toBe(2);
    // The engine sends the plan whole the first time and by version after; the second run saw "abcd".
    expect(app.engine.docs.read(s.session.ref("Plan")!)).toEqual({ title: "abcd", steps: 1 });
    expect(app.engine.mirror!.holds(s.session.ref("Plan")!)).toBe(4);
  });

  it("does not run while the field is invalid", async () => {
    vi.useFakeTimers();
    const { s, decided } = await wizard();
    await s.fill({ title: "A name far longer than twenty letters" });
    await s.blur("title");
    expect(decided()).toEqual([]);
    expect(s.invalid).toEqual({ "Plan.title": ["/ must NOT have more than 20 characters"] });
  });
});
