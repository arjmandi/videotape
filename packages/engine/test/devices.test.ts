// Reels are keyed by user and device (05 §6.2, Q62): a journey resumes on another device signed in
// as the same user, and a device that signs in again takes back its own.

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { Headless } from "../src/driver";
import { type Played, play } from "./harness";
import { NO_PYTHON } from "./python";

describe.skipIf(NO_PYTHON)("a journey across devices", () => {
  let p: Played;
  beforeAll(async () => {
    p = await play("journeys");
  }, 20_000);
  afterAll(() => p?.stop());

  const signIn = async (device: string, name = "Ada") => {
    const s = await Headless.open(p.engine, { device });
    await s.fill({ name, password: "pw" });
    await s.press("Sign in");
    return s;
  };

  it("resumes on a second device where the first one is, and each device keeps its own reel", async () => {
    const phone = await signIn("phone");
    await phone.press("Plan something");
    await phone.fill({ title: "Garden" });
    await phone.press("Name the plan");
    expect(phone.reel).toMatchObject({ head: "wizard/steps", history: ["home", "wizard/name"] });

    const laptop = await signIn("laptop");
    expect(laptop.user).toEqual({ record: "Person", id: "p1", value: { id: "p1", name: "Ada" } });
    expect(laptop.reel).toMatchObject({ head: "wizard/steps", history: ["home", "wizard/name"], hub: { current: "home" }, args: { topic: "garden" } });
    expect(laptop.doc("Plan")).toEqual({ title: "Garden", steps: 1 });
    expect(laptop.error).toBeNull();

    // Two reels now: the draft was copied, and moving on one device leaves the other where it is.
    await laptop.fill({ steps: 5 });
    expect(phone.doc("Plan").steps).toBe(1);
    await laptop.back();
    expect(laptop.place).toBe("wizard/name");
    expect(phone.place).toBe("wizard/steps");
    await laptop.back();
    expect(laptop.doc("Home")).toEqual({ id: "home-p1", greeting: "Hello, Ada", visits: 0 });
    await laptop.press("Wave");
    await phone.back();
    await phone.back();
    expect(phone.doc("Home").visits).toBe(1);                  // a shared document stays shared

    // The phone's app goes away; signing in on the phone again takes back the phone's own journey.
    await phone.press("Plan something");
    p.engine.detach(phone.session);
    const again = await signIn("phone");
    expect(again.reel).toMatchObject({ head: "wizard/name", history: ["home"] });
    expect(phone.session.closed).toBe(true);
    expect(laptop.place).toBe("home");

    // Another user has no journey yet: the sign-in goes where it says.
    const grace = await signIn("tablet", "Grace");
    expect(grace.reel).toMatchObject({ head: "home", history: [] });
    expect(grace.doc("Home").id).toBe("home-p2");

    // A device that signs out is no longer the user's journey there: a new device resumes the phone.
    await laptop.door("account");
    await laptop.press("Sign out");
    const desk = await signIn("desk");
    expect(desk.reel).toMatchObject({ head: "wizard/name", history: ["home"] });
    for (const s of [again, grace, laptop, desk]) s.close();
  });

  it("resumes a journey for a session that opens signed in, unless it opens at an address", async () => {
    const ada = { record: "Person", id: "p1", value: { id: "p1", name: "Ada" } };
    const phone = await Headless.open(p.engine, { device: "phone-2", tape: "home", user: ada });
    await phone.door("inbox");
    const watch = await Headless.open(p.engine, { device: "watch", user: ada });
    expect(watch.reel).toMatchObject({ head: "inbox", hub: { current: "inbox" } });
    const linked = await Headless.open(p.engine, { device: "car", address: "/items/i3", user: ada });
    expect(linked.place).toBe("item");
    for (const s of [phone, watch, linked]) s.close();
  });
});
