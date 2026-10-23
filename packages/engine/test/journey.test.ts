import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { APP_UNAVAILABLE, SOMETHING_WENT_WRONG } from "../src/session";
import { ADA, Client, type Played, fake, play } from "./harness";
import { NO_PYTHON } from "./python";

describe.skipIf(NO_PYTHON)("the journey runtime, with the journeys app", () => {
  let p: Played;
  beforeAll(async () => {
    p = await play("journeys");
  }, 20_000);
  afterAll(() => p?.stop());

  const open = (opts = {}) => Client.open(p.engine, opts);
  const signedIn = async () => {
    const c = await open();
    await c.fill("Login.name", "Ada");
    await c.press("Sign in", { secrets: { password: "pw" } });
    return c;
  };

  it("starts at the entry, a history root without the hub", async () => {
    const c = await open();
    expect(c.view.reel).toMatchObject({ head: "welcome", history: [], root: true, back: false, hub: null });
    expect(c.view.fields.map((f) => [f.field, f.secret])).toEqual([["Login.name", false], ["Login.password", true]]);
    expect(c.events.at(-1)).toMatchObject({ t: "frame", view: { place: "welcome" } });
  });

  it("stays on a rejection, shows the message, and clears the secret", async () => {
    const c = await open();
    await c.fill("Login.name", "Ada");
    await c.press("Sign in", { secrets: { password: "nope" } });
    expect(c.place).toBe("welcome");
    expect(c.view.status).toEqual({ pending: false, error: "Wrong password.", invalid: {} });
    expect(c.events.filter((e) => e.t === "clear")).toEqual([{ t: "clear", fields: ["Login.password"] }]);
    expect(c.session.user).toBeNull();
    expect(JSON.stringify(c.doc("Login"))).not.toContain("nope");
    expect(JSON.stringify(p.lines)).not.toContain("nope");
  });

  it("signs in with the user's record and lands on a hub destination as a history root", async () => {
    const c = await signedIn();
    expect(c.session.user).toEqual(ADA);
    expect(c.view.reel).toMatchObject({ head: "home", history: [], root: true, back: false, hub: { current: "home", destinations: ["home", "inbox", "account"] } });
    expect(c.doc("Home")).toEqual({ id: "home-p1", greeting: "Hello, Ada", visits: 0 });
    const statuses = c.events.flatMap((e) => (e.t === "status" ? [e.status.pending] : []));
    expect(statuses).toContain(true);
  });

  it("validates a submit before it reaches the app", async () => {
    const c = await open();
    const asked = p.lines.length;
    await c.press("Sign in", { secrets: { password: "pw" } });
    expect(c.place).toBe("welcome");
    expect(c.view.status.invalid).toEqual({ "Login.name": ["is required"] });
    expect(p.lines.slice(asked).some((l) => l.msg.includes("decision"))).toBe(false);
  });

  it("passes the tape's arguments and earlier frames' documents along a wizard, and back keeps the draft", async () => {
    const c = await signedIn();
    await c.press("Plan something");
    expect(c.view.reel).toMatchObject({ head: "wizard/name", history: ["home"], back: true, args: { topic: "garden" } });
    await c.press("Name the plan");
    expect(c.view.status.error).toBe("Give the plan a name.");
    await c.fill("Plan.title", "Garden plan");
    await c.press("Name the plan");
    expect(c.view.reel).toMatchObject({ head: "wizard/steps", history: ["home", "wizard/name"] });
    expect(c.doc("Plan")).toEqual({ title: "Garden plan", steps: 1 });  // the same draft
    await c.fill("Plan.steps", 3);
    await c.back();
    expect(c.place).toBe("wizard/name");
    expect(c.doc("Plan")).toEqual({ title: "Garden plan", steps: 3 });
    await c.press("Name the plan");
    await c.press("Next");
    expect(c.view.reel).toMatchObject({ head: "wizard/review", back: false, hub: { current: "home" } });
    expect(c.doc("Summary")).toEqual({ topic: "garden", text: "Garden plan in 3 steps" });
    await c.back();
    expect(c.dropped()).toContain("no history here");                 // back=False
    await c.press("Done");
    expect(c.view.reel).toMatchObject({ head: "home", history: ["home", "wizard/name", "wizard/steps", "wizard/review"] });
  });

  it("calls a tape, returns its result to then=, and leaves a call by back without one", async () => {
    const c = await signedIn();
    await c.press("Confirm");
    expect(c.view.reel).toMatchObject({ head: "confirm", calls: ["confirm"], hub: null, back: true, root: false });
    await c.press("Yes");
    expect(c.view.reel).toMatchObject({ head: "home", calls: [], hub: { current: "home" } });
    expect(c.doc("Home").greeting).toBe("Confirmed");
    await c.press("Confirm");
    await c.back();
    expect(c.view.reel).toMatchObject({ head: "home", calls: [] });
    expect(c.doc("Home").greeting).toBe("Confirmed");
    await c.press("Confirm");
    await c.press("No");
    expect(c.doc("Home").greeting).toBe("Kept");
  });

  it("keeps each hub destination's own history", async () => {
    const c = await signedIn();
    await c.press("Plan something");
    await c.door("inbox");
    expect(c.view.reel).toMatchObject({ head: "inbox", history: [], root: true, hub: { current: "inbox" } });
    await c.press("select:Inbox.items", { item: c.key("Inbox", "items", 1) });
    expect(c.view.reel).toMatchObject({ head: "item", history: ["inbox"], hub: null, args: { item_id: "i2" } });
    expect(c.doc("Item")).toEqual({ id: "i2", title: "Item i2" });
    await c.door("home");
    expect(c.dropped()).toContain("this frame shows no hub");         // hub=False
    await c.back();
    await c.door("home");
    expect(c.view.reel).toMatchObject({ head: "wizard/name", history: ["home"], hub: { current: "home" } });
    await c.door("home");                                             // the current destination starts over
    expect(c.view.reel).toMatchObject({ head: "home", history: [] });
    await c.door("inbox");
    expect(c.view.reel).toMatchObject({ head: "inbox", history: [] });
  });

  it("opens a frame by its address with its destination beneath it", async () => {
    const c = await open({ address: "/items/i9", user: ADA });
    expect(c.view.reel).toMatchObject({ head: "item", history: ["inbox"], root: false, back: true, hub: null, args: { item_id: "i9" } });
    expect(c.doc("Item")).toEqual({ id: "i9", title: "Item i9" });
    await c.back();
    expect(c.view.reel).toMatchObject({ head: "inbox", root: true, hub: { current: "inbox" } });
    expect(c.doc("Inbox").items).toHaveLength(2);                     // entered when the user got there
  });

  it("signs out to a fresh history", async () => {
    const c = await signedIn();
    await c.door("account");
    await c.press("Sign out");
    expect(c.session.user).toBeNull();
    expect(c.view.reel).toMatchObject({ head: "welcome", history: [], root: true, hub: null });
  });

  it("hands the client effects: a link, a download, a copy", async () => {
    const c = await signedIn();
    await c.press("Help");
    await c.press("Export");
    await c.press("Copy greeting");
    expect(c.effects()).toEqual([
      { type: "open", url: "https://example.com/help" },
      { type: "download", name: "home.txt", data: "Hello, Ada" },
      { type: "copy", value: "Hello, Ada" },
    ]);
    expect(c.place).toBe("home");
  });

  it("keeps a handler's changes when it stays", async () => {
    const c = await signedIn();
    await c.press("Wave");
    await c.press("Wave");
    expect(c.doc("Home").visits).toBe(2);
  });

  it("validates inputs against the frame they were made against", async () => {
    const c = await signedIn();
    const s = c.session;
    await s.input({ t: "press", seq: 1, frame: s.version, action: "action:2" });         // replayed seq
    await c.send({ t: "press", action: "action:2" }, s.version - 1);                      // stale frame
    await c.press("action:99");
    await c.fill("Home.greeting", "x");                                                   // shown, not edited
    await c.door("nowhere");
    await s.input({ t: "fill", seq: 99 });
    await c.send({ t: "press", action: "action:2", item: "x" });
    await c.press("Plan something");
    await c.fill("Plan.steps", "three");
    await c.fill("Plan.title", "A name far longer than twenty letters");
    await c.press("Name the plan", { secrets: { title: "x" } });
    expect(c.dropped()).toEqual([
      "replayed seq", "stale frame", "not an action on this frame", "not a field this frame edits", "not a hub destination",
      "malformed input", "this action is not on items", "invalid value", "secrets name a field that is not a secret of this frame",
    ]);
    expect(c.doc("Plan").title).toBe("A name far longer than twenty letters");
    expect(c.view.status.invalid).toEqual({ "Plan.title": ["/ must NOT have more than 20 characters"] });
    expect(c.doc("Home")).toBeUndefined();
  });

  it("lets go of documents the reel no longer holds", async () => {
    const before = p.engine.docs.size;
    const c = await signedIn();
    await c.press("Plan something");
    await c.door("inbox");
    expect(p.engine.docs.size).toBeGreaterThan(before);
    await c.door("account");
    await c.press("Sign out");
    p.engine.close(c.session);
    expect(p.engine.docs.size).toBe(before);
  });
});

describe("when the app fails", () => {
  it("shows the engine's error when the handler raises, and rolls its changes back", async () => {
    const app = fake("journeys", (req, a) => {
      if (req.t === "decide") {
        a.sync([{ doc: req.documents.login!.ref, ops: [{ op: "set", path: ["name"], value: "Changed" }] }], req.id);
        return { error: { type: "KeyError", message: "boom" } };
      }
      return { documents: [] };
    });
    await app.engine.ready();
    const c = await Client.open(app.engine);
    await c.fill("Login.name", "Ada");
    await c.press("Sign in", { secrets: { password: "pw" } });
    expect(c.view.status.error).toBe(SOMETHING_WENT_WRONG);
    expect(c.doc("Login")).toEqual({ name: "Ada" });
    expect(app.lines.some((l) => l.msg === "a handler raised" && l.fields?.type === "KeyError")).toBe(true);
  });

  it("refuses an outcome the handler's intent does not declare", async () => {
    const app = fake("journeys", (req) => (req.t === "decide" ? { outcome: { type: "jump", tape: "inbox" } } : { documents: [] }));
    await app.engine.ready();
    const c = await Client.open(app.engine);
    await c.fill("Login.name", "Ada");
    await c.press("Sign in", { secrets: { password: "pw" } });
    expect(c.place).toBe("welcome");
    expect(c.view.status.error).toBe(SOMETHING_WENT_WRONG);
  });

  it("fails a decision when the app goes away or takes too long", async () => {
    const app = fake("journeys", (req) => (req.t === "decide" ? "hang" : { documents: [] }), { timeoutMs: 50 });
    await app.engine.ready();
    const c = await Client.open(app.engine);
    await c.fill("Login.name", "Ada");
    await c.press("Sign in", { secrets: { password: "pw" } });
    expect(c.view.status).toMatchObject({ pending: false, error: APP_UNAVAILABLE });
    const pending = c.press("Sign in", { secrets: { password: "pw" } });
    await new Promise((r) => setTimeout(r, 5));
    expect(c.view.status.pending).toBe(true);
    app.disconnect();
    await pending;
    expect(c.view.status).toMatchObject({ pending: false, error: APP_UNAVAILABLE });
    expect(app.engine.link).toBeUndefined();
    await c.press("Sign in", { secrets: { password: "pw" } });
    expect(c.view.status.error).toBe(APP_UNAVAILABLE);
  });

  it("enters a frame with defaults when its loader fails", async () => {
    const app = fake("journeys", (req) => (req.t === "load" ? { error: { type: "OSError", message: "db down" } } : { documents: [] }));
    await app.engine.ready();
    const c = await Client.open(app.engine, { tape: "inbox", user: ADA });
    expect(c.place).toBe("inbox");
    expect(c.view.status.error).toBe(SOMETHING_WENT_WRONG);
    expect(c.doc("Inbox")).toEqual({ id: null });
  });
});

describe.skipIf(NO_PYTHON)("the journey runtime, with the sample apps", () => {
  it("hello: signs in to the workspace as a history root; a linked report is a root of its own", async () => {
    const p = await play("hello");
    try {
      const c = await Client.open(p.engine);
      expect(c.view.reel).toMatchObject({ head: "landing", root: true, hub: null });
      await c.press("Sign in");
      expect(c.view.reel).toMatchObject({ head: "login", history: ["landing"], back: true });
      await c.fill("Credentials.username", "ada@example.com");
      await c.press("Sign in", { secrets: { password: "correct horse" } });
      expect(c.view.reel).toMatchObject({ head: "workspace", history: [], root: true, back: false, hub: null });
      expect(c.session.user).toEqual({ record: "User", id: "u1", value: { id: "u1", first_name: "Ada" } });
      expect(c.doc("Workspace")).toEqual({ id: "u1", projects: [] });

      const linked = await Client.open(p.engine, { address: "/projects/p7" });
      expect(linked.view.reel).toMatchObject({ head: "report", history: [], root: true, back: false, args: { project_id: "p7" } });
      expect(linked.doc("Report")).toMatchObject({ id: "p7", title: "Q3" });
      await linked.press("All projects");
      expect(linked.view.reel).toMatchObject({ head: "workspace", history: ["report"] });
    } finally {
      await p.stop();
    }
  }, 20_000);

  it("relay: the entry is a hub destination, and a linked thread opens with Chats beneath it", async () => {
    const p = await play("relay");
    try {
      const user = { record: "User", id: "u1", value: { id: "u1", name: "Ada" } };
      const c = await Client.open(p.engine, { user });
      expect(c.view.reel).toMatchObject({ head: "chats", root: true, hub: { current: "chats" } });
      await c.press("select:Chats.conversations", { item: c.key("Chats", "conversations", 0) });
      expect(c.view.reel).toMatchObject({ head: "thread", history: ["chats"], hub: { current: "chats" }, args: { id: "c1" } });
      expect(c.doc("Conversation")).toMatchObject({ id: "c1", title: "Launch" });

      const linked = await Client.open(p.engine, { address: "/c/c2", user });
      expect(linked.view.reel).toMatchObject({ head: "thread", history: ["chats"], hub: { current: "chats" } });
      await linked.back();
      expect(linked.view.reel).toMatchObject({ head: "chats", root: true });
      expect(linked.doc("Chats").conversations).toHaveLength(2);
    } finally {
      await p.stop();
    }
  }, 20_000);
});
