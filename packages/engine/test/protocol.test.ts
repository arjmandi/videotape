import { afterEach, describe, expect, it, vi } from "vitest";
import { type AppHost, AppLink, AppUnavailable } from "../src/app-link";
import type { Intent } from "../src/intent";
import { MASK, memoryLogger } from "../src/log";
import { type SyncMessage, decodeAppMessage } from "../src/protocol";
import { listenForApps } from "../src/server";
import { rawIntent } from "./fixtures";
import { NO_PYTHON, startApp } from "./python";

class Host implements AppHost {
  intents: Intent[] = [];
  syncs: SyncMessage[] = [];
  closes = 0;
  refuse = false;
  registered(_link: AppLink, intent: Intent): void {
    if (this.refuse) throw new Error("one app at a time");
    this.intents.push(intent);
  }
  sync(_link: AppLink, msg: SyncMessage): void {
    this.syncs.push(msg);
  }
  closed(): void {
    this.closes += 1;
  }
}

function memoryLink(opts: { timeoutMs?: number } = {}) {
  const host = new Host();
  const sent: any[] = [];
  const log = memoryLogger();
  let closed: [number | undefined, string | undefined] | undefined;
  const link = new AppLink(host, { send: (t) => sent.push(JSON.parse(t)), close: (c, r) => (closed = [c, r]) }, { logger: log, ...opts });
  const say = (msg: unknown) => link.receive(JSON.stringify(msg));
  const register = () => say({ t: "register", v: 1, intent: rawIntent("relay"), sdk: { language: "python", version: "0.0.1" } });
  return { host, sent, log, link, say, register, closedWith: () => closed };
}

describe("app messages", () => {
  it("decodes what the app may say and refuses the rest without echoing it", () => {
    expect(decodeAppMessage('{"t":"ping"}')).toEqual({ ok: true, msg: { t: "ping" } });
    expect(decodeAppMessage("nope")).toEqual({ ok: false, reason: "not JSON" });
    expect(decodeAppMessage('{"t":"sync","changes":[]}')).toEqual({ ok: false, reason: "not a valid sync message" });
    const set = { op: "set", path: ["messages", { key: "~e1" }, "pending"], value: false };
    const sync = { t: "sync", decision: "r1", changes: [{ doc: { record: "Conversation", id: "c1" }, ops: [set] }] };
    expect(decodeAppMessage(JSON.stringify(sync)).ok).toBe(true);
    const bad = { ...sync, changes: [{ doc: { record: "Conversation", id: "c1", local: "x" }, ops: [set] }] };
    expect(decodeAppMessage(JSON.stringify(bad)).ok).toBe(false);
    expect(decodeAppMessage(JSON.stringify({ t: "result", id: "r1", outcome: { type: "stay" }, error: { type: "X", message: "" } })).ok).toBe(false);
  });
});

describe("an app link", () => {
  afterEach(() => vi.useRealTimers());

  it("registers an app whose intent loads, and refuses one whose intent does not", () => {
    const ok = memoryLink();
    ok.register();
    expect(ok.sent).toEqual([{ t: "registered", v: 1, app: "relay" }]);
    expect(ok.host.intents.map((i) => i.app)).toEqual(["relay"]);
    expect(ok.log.lines.some((l) => l.msg === "app registered" && l.fields?.sdk === "python 0.0.1")).toBe(true);

    const bad = memoryLink();
    bad.say({ t: "register", v: 1, intent: { ...(rawIntent("relay") as object), entry: "nowhere" }, sdk: { language: "python", version: "0" } });
    expect(bad.sent).toEqual([{ t: "error", code: "bad_intent", message: "the entry tape nowhere does not exist" }]);
    expect(bad.closedWith()).toEqual([1008, "refused"]);
    expect(bad.host.closes).toBe(1);
  });

  it("lets the host refuse an app, and answers anything before register with an error", () => {
    const l = memoryLink();
    l.say({ t: "sync", changes: [{ doc: { record: "Draft", local: "d1" }, ops: [{ op: "set", path: ["text"], value: "" }] }] });
    expect(l.sent).toEqual([{ t: "error", code: "not_registered", message: "send register first" }]);
    l.host.refuse = true;
    l.register();
    expect(l.sent[1]).toEqual({ t: "error", code: "refused", message: "one app at a time" });
  });

  it("matches results to requests and routes syncs to the host", async () => {
    const l = memoryLink();
    l.register();
    const pending = l.link.decide({ handler: "send", session: "s1", user: null, documents: {} });
    const req = l.sent[1];
    expect(req).toMatchObject({ t: "decide", id: "r1", handler: "send", session: "s1" });
    expect(l.link.isOpen("r1")).toBe(true);
    const change = { doc: { record: "Draft", local: "d1" }, ops: [{ op: "set", path: ["text"], value: "" }] };
    l.say({ t: "sync", decision: "r1", changes: [change] });
    l.say({ t: "result", id: "r1", outcome: { type: "stay" } });
    await expect(pending).resolves.toEqual({ t: "result", id: "r1", outcome: { type: "stay" } });
    expect(l.host.syncs).toEqual([{ t: "sync", decision: "r1", changes: [change] }]);
    expect(l.link.isOpen("r1")).toBe(false);
  });

  it("fails a request the app takes too long to answer, and ignores its late result", async () => {
    vi.useFakeTimers();
    const l = memoryLink({ timeoutMs: 50 });
    l.register();
    const pending = l.link.load({ loader: "load_chats", session: "s1", user: null, args: {}, documents: {} });
    vi.advanceTimersByTime(60);
    await expect(pending).rejects.toMatchObject({ code: "app_timeout" });
    l.say({ t: "result", id: "r1", documents: [] });
    expect(l.log.lines.at(-1)?.msg).toBe("a result for no open request");
  });

  it("fails every open request when the app goes away", async () => {
    const l = memoryLink();
    l.register();
    const a = l.link.decide({ handler: "send", session: "s1", user: null, documents: {} });
    const b = l.link.load({ loader: "load_chats", session: "s2", user: null, args: {}, documents: {} });
    l.link.closed();
    await expect(a).rejects.toBeInstanceOf(AppUnavailable);
    await expect(b).rejects.toMatchObject({ code: "app_gone" });
    await expect(l.link.load({ loader: "x", session: "s", user: null, args: {}, documents: {} })).rejects.toMatchObject({ code: "app_gone" });
    expect(l.host.closes).toBe(1);
  });

  it("logs the app's lines scrubbed of the secrets in play", () => {
    const l = memoryLink();
    l.register();
    void l.link.decide({ handler: "sign_in", session: "s1", user: null, documents: {} }, ["hunter2"]).catch(() => {});
    l.say({ t: "log", level: "warning", message: "login failed for ada with hunter2", logger: "services" });
    expect(l.log.lines.at(-1)).toEqual({ level: "warn", msg: `app: login failed for ada with ${MASK}`, fields: { app: "relay", logger: "services" } });
    l.link.closed();
  });

  it("drops malformed messages and says so", () => {
    const l = memoryLink();
    l.link.receive("{");
    expect(l.sent).toEqual([{ t: "error", code: "bad_message", message: "not JSON" }]);
    expect(l.log.lines[0]).toMatchObject({ level: "warn", msg: "dropped a message from the app" });
  });
});

describe.skipIf(NO_PYTHON)("the Python client over WebSocket", () => {
  it("registers, answers load and decide, and streams a decision's changes before its result", async () => {
    const host = new Host();
    const logger = memoryLogger();
    let registered!: () => void;
    const ready = new Promise<void>((r) => (registered = r));
    let link: AppLink | undefined;
    host.registered = (l, intent) => {
      host.intents.push(intent);
      link = l;
      queueMicrotask(registered);
    };
    const server = await listenForApps(host, { logger });
    const app = startApp("relay", server.url);
    try {
      await ready;
      expect(host.intents[0]?.app).toBe("relay");
      const loaded = await link!.load({ loader: "load_thread", session: "s1", user: null, args: { id: "c1" }, documents: {} });
      expect(loaded).toMatchObject({ documents: [{ record: "Conversation", value: { id: "c1", title: "Launch" } }] });
      const conv = (loaded as any).documents[0].value;
      conv.messages[0]["@key"] = "~e1";
      const user = { record: "User", id: "u1", value: { id: "u1", name: "Ada" } };
      const documents = {
        conv: { ref: { record: "Conversation", id: "c1" }, value: conv },
        draft: { ref: { record: "Draft", local: "d1" }, value: { text: "On my way" } },
      };
      let order: string[] = [];
      host.sync = (_l, msg) => {
        host.syncs.push(msg);
        order.push(`sync ${msg.decision}`);
      };
      const result = await link!.decide({ handler: "send", session: "s1", user, documents }).then((r) => (order.push("result"), r));
      expect(result).toMatchObject({ outcome: { type: "stay" } });
      expect(order).toEqual(["sync r2", "sync r2", "result"]);
      expect(host.syncs[0]!.changes.map((c) => c.doc)).toEqual([{ record: "Conversation", id: "c1" }, { record: "Draft", local: "d1" }]);

      order = [];
      host.syncs = [];
      const draft = { ...documents.draft, value: { text: "fail: now" } };
      const failed = await link!.decide({ handler: "send", session: "s1", user, documents: { ...documents, draft } }).then((r) => (order.push("result"), r));
      expect(failed).toMatchObject({ error: { type: "ConnectionError", message: "the message service is down" } });
      expect(order).toEqual(["sync r3", "result"]);
      expect(logger.lines.some((l) => l.level === "error" && l.msg.startsWith("app: decide send raised"))).toBe(true);
    } finally {
      await app.stop();
      await server.close();
    }
  }, 20_000);

  it("keeps a secret out of everything the app says, even when the handler leaks it", async () => {
    const host = new Host();
    const logger = memoryLogger();
    let link: AppLink | undefined;
    let registered!: () => void;
    const ready = new Promise<void>((r) => (registered = r));
    host.registered = (l, intent) => {
      host.intents.push(intent);
      link = l;
      queueMicrotask(registered);
    };
    const server = await listenForApps(host, { logger });
    const app = startApp("hello", server.url);
    try {
      await ready;
      const creds = { ref: { record: "Credentials", local: "d1" }, value: { username: "ada@example.com", password: "wrong-horse-9" } };
      const result = await link!.decide({ handler: "sign_in", session: "s1", user: null, documents: { c: creds } }, ["wrong-horse-9"]);
      expect(result).toEqual({ t: "result", id: "r1", reject: { message: "That email and password do not match." } });
      const ok = await link!.decide({ handler: "sign_in", session: "s1", user: null, documents: { c: { ...creds, value: { ...creds.value, password: "correct horse" } } } }, ["correct horse"]);
      expect(ok).toMatchObject({ outcome: { type: "jump", tape: "workspace", sign_in: { record: "User", id: "u1", value: { id: "u1", first_name: "Ada" } } } });
      expect(JSON.stringify(logger.lines)).not.toMatch(/wrong-horse-9|correct horse/);
      expect(app.output.join("")).not.toMatch(/wrong-horse-9|correct horse/);
    } finally {
      await app.stop();
      await server.close();
    }
  }, 20_000);
});
