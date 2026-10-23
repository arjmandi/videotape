// The brief's "done when", played with the headless driver against the sample apps' Python processes.

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { Headless } from "../src/driver";
import { SOMETHING_WENT_WRONG } from "../src/session";
import { type Played, play } from "./harness";
import { NO_PYTHON } from "./python";

describe.skipIf(NO_PYTHON)("hello", () => {
  let p: Played;
  beforeAll(async () => {
    p = await play("hello");
  }, 20_000);
  afterAll(() => p?.stop());

  it("signs in with its fake services and lands on the workspace as a history root", async () => {
    const s = await Headless.open(p.engine);
    await s.press("Sign in");                                       // the landing's action
    expect(s.at("login")).toBe(true);
    await s.fill({ username: "ada@example.com", password: "correct horse" });
    await s.press("Sign in");                                       // the login frame's submit
    expect(s.at("workspace")).toBe(true);
    expect(s.reel).toMatchObject({ head: "workspace", history: [], root: true, back: false });
    expect(s.user).toEqual({ record: "User", id: "u1", value: { id: "u1", first_name: "Ada" } });
    expect(s.doc("Workspace")).toEqual({ id: "u1", projects: [] });
    expect(s.error).toBeNull();
    expect(s.secret("password")).toBe("");
  });

  it("stays on a wrong password, shows the error, and clears the secret", async () => {
    const s = await Headless.open(p.engine, { tape: "login" });
    await s.fill({ username: "ada@example.com", password: "nope-not-it" });
    expect(s.secret("password")).toBe("nope-not-it");               // held by the client, as a secure editor does
    await s.press("Sign in");
    expect(s.at("login")).toBe(true);
    expect(s.error).toBe("That email and password do not match.");
    expect(s.secret("password")).toBe("");
    expect(s.doc("Credentials")).toEqual({ username: "ada@example.com" });
    expect(s.user).toBeNull();
    const everything = JSON.stringify([p.lines, p.app.output, p.engine.docs.snapshot(), s.events]);
    expect(everything).not.toContain("nope-not-it");
  });
});

describe.skipIf(NO_PYTHON)("relay", () => {
  let p: Played;
  beforeAll(async () => {
    p = await play("relay");
  }, 20_000);
  afterAll(() => p?.stop());

  const ada = { record: "User", id: "u1", value: { id: "u1", name: "Ada" } };
  const grace = { record: "User", id: "u2", value: { id: "u2", name: "Grace" } };
  const last = (c: { value: any }) => c.value.messages.at(-1);
  const words = (m: any) => m.text.blocks[0].spans[0].text;

  it("two sessions showing one conversation both see a sent message tentative, then confirmed", async () => {
    const a = await Headless.open(p.engine, { address: "/c/c1", user: ada });
    const b = await Headless.open(p.engine, { address: "/c/c1", user: grace });
    const before = a.doc("Conversation").messages.length;
    await a.fill({ text: "On my way" });
    await a.press("Send");
    for (const s of [a, b]) {
      const seen = s.changesTo("Conversation");
      expect(seen.map((c) => c.state)).toEqual(["tentative", "tentative", "confirmed"]);
      expect(seen[0]!.tentative).toBe(true);
      expect(last(seen[0]!)).toMatchObject({ author: { id: "u1", name: "Ada" }, pending: true, sent_at: null });
      expect(words(last(seen[0]!))).toBe("On my way");
      expect(seen[2]!.tentative).toBe(false);
      expect(last(seen[2]!)).toMatchObject({ pending: false, sent_at: expect.stringMatching(/^2\d{3}-/) });
      expect(s.doc("Conversation").messages).toHaveLength(before + 1);
      expect(s.tentative("Conversation")).toBe(false);
    }
    expect(a.doc("Draft")).toEqual({ text: "" });
    expect(b.changesTo("Draft")).toEqual([]);                       // the draft is Ada's own
  });

  it("a handler that raises rolls the message back in both", async () => {
    const a = await Headless.open(p.engine, { address: "/c/c1", user: ada });
    const b = await Headless.open(p.engine, { address: "/c/c1", user: grace });
    const before = a.doc("Conversation").messages.length;
    await a.fill({ text: "fail: on my way" });
    await a.press("Send");
    for (const s of [a, b]) {
      const seen = s.changesTo("Conversation");
      expect(seen.map((c) => c.state)).toEqual(["tentative", "rolledback"]);
      expect(seen[0]!.value.messages).toHaveLength(before + 1);
      expect(seen[1]!.value.messages).toHaveLength(before);
      expect(s.doc("Conversation").messages).toHaveLength(before);
    }
    expect(a.error).toBe(SOMETHING_WENT_WRONG);
    expect(a.doc("Draft")).toEqual({ text: "fail: on my way" });   // the draft is back as it was
    expect(b.error).toBeNull();
  });
});
