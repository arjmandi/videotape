import { execFileSync } from "node:child_process";
import { describe, expect, it } from "vitest";
import { INTENT_FORMAT, IntentError, loadIntent, placeName } from "../src/intent";
import { KEY, Records, stripKeys } from "../src/records";
import { python } from "../scripts/python.mjs";
import { SAMPLES, intent, rawIntent } from "./fixtures";

const mutate = (name: string, change: (i: any) => void): unknown => {
  const raw = structuredClone(rawIntent(name)) as any;
  change(raw);
  return raw;
};

const issues = (fn: () => unknown): string[] => {
  try {
    fn();
  } catch (e) {
    if (e instanceof IntentError) return e.issues;
    throw e;
  }
  return [];
};

describe("loading intent", () => {
  it.each(SAMPLES)("loads the %s sample as the SDK wrote it", (name) => {
    const i = intent(name);
    expect(i.format).toBe(INTENT_FORMAT);
    expect(i.tapes.length).toBeGreaterThan(0);
  });

  it("reads JSON text as well as a parsed value", () => {
    const text = JSON.stringify(rawIntent("hello"));
    expect(loadIntent(text).app).toBe("hello");
  });

  it("refuses what is not JSON, not an object, or another format", () => {
    expect(issues(() => loadIntent("{nope"))[0]).toMatch(/^not JSON/);
    expect(issues(() => loadIntent([]))).toEqual(["the intent is not a JSON object"]);
    expect(issues(() => loadIntent(mutate("hello", (i) => (i.format = "videotape.intent/1"))))[0]).toMatch(/this engine plays videotape.intent\/2/);
  });

  it("validates against the schema the SDK publishes", () => {
    const found = issues(() => loadIntent(mutate("hello", (i) => (i.tapes[0].frames[0].components = "none"))));
    expect(found[0]).toMatch(/^schema: \/tapes\/0\/frames\/0\/components/);
    expect(issues(() => loadIntent(mutate("hello", (i) => delete i.handlers)))[0]).toMatch(/^schema: .*handlers/);
  });

  it("resolves every name the runtime will look up", () => {
    const broken = mutate("hello", (i) => {
      i.entry = "nowhere";
      i.tapes[1].frames[0].submit.handler = "missing";
      i.tapes[3].frames[0].enter.loader = "gone";
      i.tapes[0].frames[0].actions[0].target.tape = "lost";
      i.tapes[2].frames[0].id = "sent";
    });
    expect(issues(() => loadIntent(broken))).toEqual([
      "tape reset has two frames named sent",
      "the entry tape nowhere does not exist",
      'landing (action "Sign in") goes to the tape lost, which does not exist',
      "login names the handler missing, which the intent does not carry",
      "workspace names the loader gone, which the intent does not carry",
    ]);
  });

  it("checks records, hub destinations, and under", () => {
    const broken = mutate("relay", (i) => {
      i.hub[2].tape = "nope";
      i.tapes[1].frames[0].under = "settings";
      i.tapes[1].frames[0].shows[0].record = "Unknown";
      i.records.Conversation["x-vt"].id = "slug";
    });
    expect(issues(() => loadIntent(broken))).toEqual([
      "the hub names the tape nope, which does not exist",
      "thread names the record Unknown, which the intent does not carry",
      "thread is under settings, which is not a hub destination",
      "record Conversation names slug as its id, which it does not have",
    ]);
  });

  it("names places as the SDK's graph does", () => {
    const i = intent("hello");
    const names = i.tapes.flatMap((t) => t.frames.map((f) => placeName(t, f)));
    expect(names).toEqual(["landing", "login", "reset/ask", "reset/sent", "workspace", "report"]);
    for (const e of i.edges) expect(names).toContain(e.from);
  });

  it.skipIf(!python())("matches what the SDK produces today", () => {
    expect(() => execFileSync(process.execPath, [new URL("../scripts/intents.mjs", import.meta.url).pathname, "--check"])).not.toThrow();
  });
});

describe("records", () => {
  const records = new Records(intent("relay"));

  it("finds identities and secrets", () => {
    expect(records.idField("Conversation")).toBe("id");
    expect(records.idField("Draft")).toBeUndefined();
    const hello = new Records(intent("hello"));
    expect(hello.secretFields("Credentials")).toEqual(["password"]);
    expect(hello.isSecret("Credentials", "username")).toBe(false);
  });

  it("starts documents from their defaults", () => {
    expect(records.defaults("Draft")).toEqual({ text: "" });
    expect(records.defaults("Conversation")).toEqual({ id: null, typing: null });
  });

  it("validates documents, fields, and items against the record schemas", () => {
    const user = { id: "u1", name: "Ada" };
    const text = { blocks: [{ kind: "paragraph", spans: [{ text: "hi" }] }] };
    const message = { author: user, text, sent_at: "2026-10-23T10:00:00Z", pending: false };
    expect(records.validate("Conversation", { id: "c1", title: "T", messages: [message] })).toEqual([]);
    expect(records.validate("Conversation", { id: "c1", messages: [] })).toEqual(["/ must have required property 'title'"]);
    expect(records.validateField("Conversation", "title", 5)).toEqual(["/ must be string"]);
    expect(records.validateField("Conversation", "typing", null)).toEqual([]);
    expect(records.validateItem("Conversation", "messages", { ...message, [KEY]: "~e1" })).toEqual([]);
    expect(records.validateItem("Conversation", "messages", { ...message, sent_at: "yesterday" })).toEqual(['/sent_at must match format "date-time"']);
  });

  it("keys the record items of lists by their Id, or with a fresh key", () => {
    const crm = new Records(intent("crm"));
    let n = 0;
    const mint = () => `~e${++n}`;
    const conv: any = { id: "c1", title: "T", messages: [{ text: "a" }, { text: "b", [KEY]: "kept" }] };
    records.assignKeys("Conversation", conv, mint);
    expect(conv.messages.map((m: any) => m[KEY])).toEqual(["~e1", "kept"]);
    const pipeline: any = { deals: [{ id: "d1" }, { id: null }] };
    crm.assignKeys("Pipeline", pipeline, mint);
    expect(pipeline.deals.map((d: any) => d[KEY])).toEqual(["d1", "~e2"]);
    expect(stripKeys(pipeline)).toEqual({ deals: [{ id: "d1" }, { id: null }] });
  });

  it("locates paths of fields and items", () => {
    expect(records.locate("Conversation", ["title"])).toMatchObject({ record: "Conversation", field: "title", item: false });
    expect(records.locate("Conversation", ["messages", { key: "k" }])).toMatchObject({ record: "Conversation", field: "messages", item: true });
    expect(records.locate("Conversation", ["messages", { key: "k" }, "pending"])).toMatchObject({ record: "Message", field: "pending" });
    expect(records.locate("Conversation", ["messages", { key: "k" }, "author", "name"])).toMatchObject({ record: "User", field: "name" });
    expect(records.locate("Conversation", ["nope"])).toBeUndefined();
    expect(records.locate("Conversation", ["title", "x"])).toBeUndefined();
  });
});
