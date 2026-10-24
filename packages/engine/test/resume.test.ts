// Kept journeys after a release (05 §6.2, Q73): resume at the deepest place the intent still has.

import { describe, expect, it } from "vitest";
import { Headless } from "../src/driver";
import { Engine } from "../src/engine";
import { Places, Reel } from "../src/journey";
import type { KeptJourney, KeptStep } from "../src/journeys";
import { Records } from "../src/records";
import { memoryLogger } from "../src/log";
import { intent } from "./fixtures";
import { NO_PYTHON, startApp } from "./python";

const journeys = intent("journeys");
const places = new Places(journeys, new Records(journeys));
const at = (visit: number, tape: string, frame: string | null = null, args = {}): KeptStep => ({ visit, tape, frame, args });
const kept = (k: Partial<Omit<KeptJourney, "user" | "device" | "savedAt">>) => ({ head: at(1, "home"), history: [], root: "home", calls: [], stacks: [], ...k });

function resumed(k: ReturnType<typeof kept>) {
  const reel = new Reel(places);
  reel.start("welcome");
  const ok = reel.resume(k);
  return { ok, reel, view: reel.describe() };
}

describe("resuming a kept journey after a release (Q73)", () => {
  it("resumes as it was when every place still exists", () => {
    const { ok, view, reel } = resumed(kept({
      head: at(2, "wizard", "steps", { topic: "garden" }),
      history: [at(1, "home"), at(2, "wizard", "name", { topic: "garden" })],
    }));
    expect(ok).toBe(true);
    expect(view).toMatchObject({ head: "wizard/steps", history: ["home", "wizard/name"], hub: { current: "home" }, args: { topic: "garden" } });
    expect(reel.history[1]!.visit).toBe(reel.head.visit);          // steps of one visit share it
    expect(reel.head.entered).toBe(false);                          // loaders run again
  });

  it("resumes at the deepest place that survives, with the history beneath it", () => {
    const { ok, view } = resumed(kept({
      head: at(2, "wizard", "gone", { topic: "garden" }),
      history: [at(1, "home"), at(2, "wizard", "name", { topic: "garden" })],
    }));
    expect(ok).toBe(true);
    expect(view).toMatchObject({ head: "wizard/name", history: ["home"], args: { topic: "garden" } });
  });

  it("drops only what was removed, below the head too", () => {
    const { view } = resumed(kept({
      head: at(3, "item", null, { item_id: "i1" }),
      history: [at(1, "inbox"), at(2, "removed-tape")],
      root: "inbox",
    }));
    expect(view).toMatchObject({ head: "item", history: ["inbox"], hub: null });
  });

  it("leaves a call none of whose places survive, and keeps one that has", () => {
    const call = { tape: "confirm", then: "answered", caller: at(1, "home"), history: [], root: "home" };
    const left = resumed(kept({ head: at(2, "confirm", "gone"), calls: [call], root: null }));
    expect(left.view).toMatchObject({ head: "home", calls: [], hub: { current: "home" } });
    const gone = resumed(kept({ head: at(2, "gone-tape"), calls: [{ ...call, tape: "gone-tape" }], root: null }));
    expect(gone.view).toMatchObject({ head: "home", calls: [] });
    const kept_ = resumed(kept({ head: at(2, "confirm"), calls: [call], root: null }));
    expect(kept_.view).toMatchObject({ head: "confirm", calls: ["confirm"], hub: null });
    expect(kept_.reel.calls[0]!.then).toBe("answered");
  });

  it("keeps what survives of each saved hub history, and none of a destination that is gone", () => {
    const { reel } = resumed(kept({
      stacks: [
        { tape: "inbox", head: at(5, "item", "gone"), history: [at(4, "inbox")] },
        { tape: "not-a-destination", head: at(6, "home"), history: [] },
      ],
    }));
    reel.door("inbox");
    expect(reel.describe()).toMatchObject({ head: "inbox", history: [] });
    expect(reel.save().stacks.has("not-a-destination")).toBe(false);
  });

  it("does not resume when nothing survives", () => {
    const { ok, view } = resumed(kept({ head: at(1, "gone"), history: [at(2, "wizard", "nope")] }));
    expect(ok).toBe(false);
    expect(view.head).toBe("welcome");
  });
});

describe.skipIf(NO_PYTHON)("a kept journey across a release", () => {
  it("resumes at the deepest place the new release still has", async () => {
    const engine = new Engine({ logger: memoryLogger() });
    const server = await engine.listen();
    let app = startApp("journeys", server.url);
    try {
      await engine.ready();
      const ada = { record: "Person", id: "p1", value: { id: "p1", name: "Ada" } };
      const phone = await Headless.open(engine, { device: "phone", tape: "home", user: ada });
      await phone.press("Plan something");
      await phone.fill({ title: "Garden" });
      await phone.press("Name the plan");
      expect(phone.reel).toMatchObject({ head: "wizard/steps", history: ["home", "wizard/name"] });

      // The next release drops wizard/steps; the app process restarts with it.
      await app.stop();
      app = startApp("journeys_next", server.url);
      await expect.poll(() => engine.link !== undefined && engine.places.frameIndex("wizard", "steps") === -1, { timeout: 10_000 }).toBe(true);

      const laptop = await Headless.open(engine, { device: "laptop", user: ada });
      expect(laptop.reel).toMatchObject({ head: "wizard/name", history: ["home"], hub: { current: "home" }, args: { topic: "garden" } });
      expect(laptop.error).toBeNull();
      await laptop.back();
      expect(laptop.doc("Home")).toMatchObject({ id: "home-p1" });
    } finally {
      await app.stop();
      await server.close();
    }
  }, 30_000);
});
