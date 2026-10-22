import { describe, expect, it } from "vitest";
import { applyPatch, getPath, setPath, traceReads } from "../src";

describe("data paths", () => {
  it("reads nested values and returns undefined for missing ones", () => {
    const d = { a: { b: { c: 1 } }, list: [1, 2] };
    expect(getPath(d, "a.b.c")).toBe(1);
    expect(getPath(d, "a.x.c")).toBeUndefined();
    expect(getPath(d, "list.1")).toBe(2);
  });

  it("sets without mutating and creates missing parents", () => {
    const d = { a: { keep: true } };
    const out = setPath(d, "a.b.c", 2);
    expect(out).toEqual({ a: { keep: true, b: { c: 2 } } });
    expect(d).toEqual({ a: { keep: true } });
  });

  it("replaces a scalar parent with an object", () => {
    expect(setPath({ a: 1 }, "a.b", 2)).toEqual({ a: { b: 2 } });
  });

  it("applies a path → value patch in order", () => {
    expect(applyPatch({}, { "login.error": "Wrong", user: { name: "Ada" } })).toEqual({ login: { error: "Wrong" }, user: { name: "Ada" } });
  });

  it("refuses prototype-polluting paths", () => {
    expect(() => setPath({}, "__proto__.polluted", 1)).toThrow();
    expect(() => applyPatch({}, { "a.constructor.prototype": 1 })).toThrow();
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
  });
});

describe("traceReads", () => {
  it("records the leaf paths a flavour function reads", () => {
    expect(traceReads((d) => ({ mood: d.user.plan === "pro" ? "warm" : "cool", w: d.forecast.kind }))).toEqual([
      "forecast.kind", "user.plan",
    ]);
  });

  it("records reads made before a throw", () => {
    expect(traceReads((d) => {
      void d.a.b;
      throw new Error("boom");
    })).toEqual(["a.b"]);
  });

  it("records template-literal reads", () => {
    expect(traceReads((d) => `${d.city.name}`)).toEqual(["city.name"]);
  });
});
