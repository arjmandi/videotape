// Journeys across devices (05 §6.2, Q62, Q69, Q70): a signed-in journey is kept, positions and
// history only, for the app's keep_journeys (7 days in the journeys app); any device the user signs
// in on resumes the most recent one, with its loaders run again; resume=False lands where it points.

import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { Headless } from "../src/driver";
import { Engine } from "../src/engine";
import { MemoryJourneys } from "../src/journeys";
import { memoryLogger } from "../src/log";
import { type Played, play } from "./harness";
import { NO_PYTHON, startApp } from "./python";

describe.skipIf(NO_PYTHON)("a journey across devices", () => {
  let p: Played;
  let opened: Headless[] = [];
  beforeAll(async () => {
    p = await play("journeys");
  }, 20_000);
  afterAll(() => p?.stop());
  afterEach(() => {
    for (const s of opened) s.close();
    opened = [];
    (p.engine.journeys as MemoryJourneys).clear();
  });

  const open = async (opts: Parameters<typeof Headless.open>[1]) => {
    const s = await Headless.open(p.engine, opts);
    opened.push(s);
    return s;
  };
  const signIn = async (device: string, name = "Ada") => {
    const s = await open({ device });
    await s.fill({ name, password: "pw" });
    await s.press("Sign in");
    return s;
  };

  it("resumes on any device the most recent journey, positions only, and each device then goes its own way", async () => {
    const phone = await signIn("phone");
    await phone.press("Plan something");
    await phone.fill({ title: "Garden" });
    await phone.press("Name the plan");
    expect(phone.reel).toMatchObject({ head: "wizard/steps", history: ["home", "wizard/name"] });

    const laptop = await signIn("laptop");
    expect(laptop.user).toEqual({ record: "Person", id: "p1", value: { id: "p1", name: "Ada" } });
    expect(laptop.reel).toMatchObject({ head: "wizard/steps", history: ["home", "wizard/name"], hub: { current: "home" }, args: { topic: "garden" } });
    expect(laptop.doc("Plan")).toEqual({ title: "", steps: 1 });        // documents are never kept: the draft starts afresh
    expect(laptop.error).toBeNull();

    await laptop.fill({ steps: 5 });
    expect(phone.doc("Plan").steps).toBe(1);
    await laptop.back();
    expect(laptop.place).toBe("wizard/name");
    expect(phone.place).toBe("wizard/steps");
    await laptop.back();                                                // the loader runs again on the way back
    expect(laptop.doc("Home")).toEqual({ id: "home-p1", greeting: "Hello, Ada", visits: 0 });
    await laptop.press("Wave");
    await phone.back();
    await phone.back();
    expect(phone.doc("Home").visits).toBe(1);                           // a shared document stays shared

    // The most recent journey wins, whichever device made it: the phone moved last.
    await phone.press("Plan something");
    const again = await signIn("tablet");
    expect(again.reel).toMatchObject({ head: "wizard/name", history: ["home"] });

    // Another user has no journey yet: the sign-in goes where it says.
    const grace = await signIn("watch", "Grace");
    expect(grace.reel).toMatchObject({ head: "home", history: [] });
    expect(grace.doc("Home").id).toBe("home-p2");
  });

  it("keeps only positions and history, never a document", async () => {
    const phone = await signIn("phone");
    await phone.press("Plan something");
    await phone.fill({ title: "Secret garden plans" });
    await phone.press("Name the plan");
    await phone.press("Wave");
    const kept = (p.engine.journeys as MemoryJourneys).all();
    expect(kept).toHaveLength(1);
    const [j] = kept;
    expect(Object.keys(j!).sort()).toEqual(["calls", "device", "head", "history", "root", "savedAt", "stacks", "user"]);
    expect(Object.keys(j!.head).sort()).toEqual(["args", "frame", "tape", "visit"]);
    expect(j).toMatchObject({ user: "Person#p1", device: "phone", root: "home", head: { tape: "wizard", frame: "steps", args: { topic: "garden" } } });
    const text = JSON.stringify(kept);
    expect(text).not.toContain("Secret garden plans");
    expect(text).not.toContain("Hello, Ada");
  });

  it("keeps a journey after the session ends, until the user signs out on that device", async () => {
    const phone = await signIn("phone");
    await phone.press("Plan something");
    phone.close();
    const later = await signIn("phone");
    expect(later.place).toBe("wizard/name");
    await later.door("home");
    await later.door("account");
    await later.press("Sign out");
    const next = await signIn("laptop");
    expect(next.reel).toMatchObject({ head: "home", history: [] });
  });

  it("brings a draft back in a new session when the app keeps it in its own services (Q72)", async () => {
    const phone = await signIn("phone", "Grace");
    await phone.press("Plan something");
    expect(phone.doc("Plan")).toEqual({ title: "", steps: 1 });
    await phone.fill({ title: "Roses" });                            // commit="change": on_change saves it
    await phone.blur("title");                                       // at once on blur, rather than after the pause
    expect(phone.error).toBeNull();
    expect(JSON.stringify((p.engine.journeys as MemoryJourneys).all())).not.toContain("Roses");   // never kept here
    phone.close();
    (p.engine.journeys as MemoryJourneys).clear();                  // no journey to resume: the loader alone brings it back
    const laptop = await signIn("laptop", "Grace");
    expect(laptop.place).toBe("home");
    await laptop.press("Plan something");
    expect(laptop.doc("Plan")).toEqual({ title: "Roses", steps: 1 });
  });

  it("saves a draft while a required field is still empty, and brings it back unfinished (Q75)", async () => {
    const ada = { record: "Person", id: "p1", value: { id: "p1", name: "Ada" } };
    const s = await open({ device: "phone", tape: "notes", user: ada });
    expect(s.doc("Note")).toEqual({ body: "" });
    await s.fill({ body: "half a thought" });
    await s.blur("body");                                           // save_note takes vt.Draft[Note]: it runs without a title
    expect(s.error).toBeNull();
    const later = await open({ device: "laptop", tape: "notes", user: ada });
    expect(later.doc("Note")).toEqual({ body: "half a thought" });
    await later.press("Keep");                                      // keep_note takes Note: the submit checks first
    expect(later.invalid).toEqual({ "Note.title": ["is required"] });
    expect(later.place).toBe("notes");
    await later.fill({ title: "Plan" });
    await later.press("Keep");
    expect(later.place).toBe("home");
  });

  it("lands where a sign-in points when it says resume=False (Q70)", async () => {
    const phone = await signIn("phone");
    await phone.press("Plan something");
    const laptop = await open({ device: "laptop" });
    await laptop.fill({ name: "Ada" });
    await laptop.press("Sign in here", { secrets: { password: "pw" } });
    expect(laptop.user?.id).toBe("p1");
    expect(laptop.reel).toMatchObject({ head: "home", history: [] });
  });

  it("resumes for a session that opens signed in, unless it opens at an address or a tape", async () => {
    const ada = { record: "Person", id: "p1", value: { id: "p1", name: "Ada" } };
    const phone = await open({ device: "phone", tape: "home", user: ada });
    await phone.door("inbox");
    const watch = await open({ device: "watch", user: ada });
    expect(watch.reel).toMatchObject({ head: "inbox", hub: { current: "inbox" } });
    const linked = await open({ device: "car", address: "/items/i3", user: ada });
    expect(linked.place).toBe("item");
  });
});

describe.skipIf(NO_PYTHON)("how long a journey is kept", () => {
  it("forgets a journey older than the app's keep_journeys", async () => {
    let clock = Date.parse("2026-10-24T09:00:00Z");
    const engine = new Engine({ logger: memoryLogger(), now: () => clock });
    const server = await engine.listen();
    const app = startApp("journeys", server.url);
    try {
      await engine.ready();
      expect(engine.keepMs).toBe(7 * 24 * 3600 * 1000);
      const ada = { record: "Person", id: "p1", value: { id: "p1", name: "Ada" } };
      const phone = await Headless.open(engine, { device: "phone", tape: "home", user: ada });
      await phone.door("inbox");
      clock += 6 * 24 * 3600 * 1000;
      const soon = await Headless.open(engine, { device: "laptop", user: ada });
      expect(soon.place).toBe("inbox");
      clock += 8 * 24 * 3600 * 1000;                                   // more than 7 days after anything was saved
      const late = await Headless.open(engine, { device: "tablet", user: ada });
      expect(late.place).toBe("welcome");
    } finally {
      await app.stop();
      await server.close();
    }
  }, 20_000);
});
