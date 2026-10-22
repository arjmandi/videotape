// The start of M2, against fakes: region validation, re-roll and patching,
// budgets with flat fallback, cache hit rate, and ahead-of-time rendering.
import sharp from "sharp";
import { describe, expect, it } from "vitest";
import {
  type SceneAsset, type SceneRenderer, type SceneRequest, type ServerMessage, button, dusk, frame, input, layout, text,
} from "@videotape/core";
import demo from "../../../apps/site/tapes";
import { services } from "../../../apps/site/services";
import { MemoryCache, patchRegions, regionStats, renderAhead, sharpValidator } from "../src";
import { harness, settle } from "./harness";

const wf = layout(frame("f", { layout: "form", components: [
  text("title", "Sign in"), input("user", { label: "User" }), button("go", "Go", { on: { press: "x" } }),
] }), "desktop", dusk);

const SMALL = { w: 480, h: 270 };

async function solid(color: string, size = SMALL): Promise<Uint8Array> {
  return new Uint8Array(await sharp({ create: { width: size.w, height: size.h, channels: 3, background: color } }).png().toBuffer());
}

/** Coarse grey texture: 6 px blocks of random brightness, like busy scenery behind a field. */
async function noise(seed = 1, size = SMALL): Promise<Uint8Array> {
  let s = seed;
  const buf = Buffer.alloc(size.w * size.h * 3);
  const block = new Map<number, number>();
  for (let y = 0; y < size.h; y++) {
    for (let x = 0; x < size.w; x++) {
      const b = Math.floor(y / 6) * 1000 + Math.floor(x / 6);
      if (!block.has(b)) {
        s = (s * 1103515245 + 12345) & 0x7fffffff;
        block.set(b, s & 255);
      }
      buf.fill(block.get(b)!, (y * size.w + x) * 3, (y * size.w + x) * 3 + 3);
    }
  }
  return new Uint8Array(await sharp(buf, { raw: { width: size.w, height: size.h, channels: 3 } }).png().toBuffer());
}

/**
 * A pretend generative backend: returns `images[i]` on its i-th call for a key (the last
 * one repeats), and records every call. Prefetches call it too, so tests filter by key.
 */
function fakeRenderer(images: Array<() => Promise<Uint8Array>>, opts: { delayMs?: number; fail?: boolean } = {}) {
  const log: Array<{ key: string; seed: number }> = [];
  const r: SceneRenderer & { calls: () => number; seedsFor: (key: string) => number[] } = {
    id: "fake-gen", version: "1", kind: "scene",
    calls: () => log.length,
    seedsFor: (key) => log.filter((c) => c.key === key).map((c) => c.seed),
    async render(req: SceneRequest, signal: AbortSignal): Promise<SceneAsset> {
      const n = log.filter((c) => c.key === req.key).length;
      log.push({ key: req.key, seed: req.seed });
      expect(req.condition.png.byteLength).toBeGreaterThan(0);
      expect(req.masks.reserved.byteLength).toBeGreaterThan(0);
      if (opts.delayMs) await new Promise((res) => setTimeout(res, opts.delayMs));
      signal.throwIfAborted();
      if (opts.fail) throw new Error("backend down");
      const make = images[Math.min(n, images.length - 1)]!;
      return { key: req.key, mime: "image/png", bytes: await make(), meta: {} };
    },
  };
  return r;
}

const types = (ms: ServerMessage[]) => ms.map((m) => m.t);

describe("region validation (spec §7.3)", () => {
  it("passes a calm dark field", async () => {
    const stats = await regionStats(await solid("#101014"), wf, dusk);
    expect(stats.length).toBeGreaterThan(0);
    expect(stats.every((s) => s.ok)).toBe(true);
  });

  it("fails a noisy field on variance", async () => {
    const stats = await regionStats(await noise(), wf, dusk);
    expect(stats.every((s) => !s.ok && s.spread > 24)).toBe(true);
  });

  it("fails a mid-grey field on contrast with the light foreground", async () => {
    const stats = await regionStats(await solid("#8a8a8a"), wf, dusk);
    expect(stats.every((s) => !s.ok && s.spread === 0 && s.contrast < 4.5)).toBe(true);
  });

  it("checks only reserved content regions, not surfaces or panels", async () => {
    const ids = (await regionStats(await solid("#101014"), wf, dusk)).map((s) => s.id).sort();
    expect(ids).toEqual(["title", "user"]);
  });

  it("patches the failing regions only", async () => {
    const patched = await patchRegions(await noise(), wf, dusk, ["user"], "png");
    const after = await regionStats(patched, wf, dusk);
    expect(after.find((s) => s.id === "user")!.ok).toBe(true);
    expect(after.find((s) => s.id === "title")!.ok).toBe(false);
  });
});

describe("re-roll and patch", () => {
  it("re-rolls with the next seed until a scene passes (s, s+1, s+2)", async () => {
    const r = fakeRenderer([() => noise(1), () => noise(2), () => solid("#101014")]);
    const h = harness(demo, services, { renderers: [r], validator: sharpValidator(), debug: true, budgets: { firstRenderMs: 30_000 } });
    await h.hello();
    expect(r.seedsFor(h.render().key)).toEqual([dusk.seed, dusk.seed + 1, dusk.seed + 2]);
    expect(h.render().fallback).toBe(false);
    expect(h.render().debug).toMatchObject({ renderer: "fake-gen", rerolls: 2 });
    expect(h.render().debug).not.toHaveProperty("patched");
  });

  it("after three re-rolls, keeps the scene and fills only the failing regions", async () => {
    const r = fakeRenderer([() => noise(7)]);
    const h = harness(demo, services, { renderers: [r], validator: sharpValidator(), debug: true, budgets: { firstRenderMs: 30_000 } });
    await h.hello();
    expect(r.seedsFor(h.render().key)).toEqual([0, 1, 2, 3].map((i) => dusk.seed + i));
    expect(h.engine.host.stats.patched).toBeGreaterThanOrEqual(1);
    const dbg = h.render().debug as { rerolls: number; patched: string[] };
    expect(dbg.rerolls).toBe(3);
    expect(dbg.patched.sort()).toEqual(["headline", "signin", "sub", "wordmark", "github"].sort());
    // The stored scene now passes in exactly those regions.
    const file = h.render().layers[0]!.url.slice(3);
    const stored = (await h.engine.cache.getAsset(file))!;
    const landing = h.engine.plan({ tape: "landing", frame: "home" }, {}, "desktop").wireframe;
    expect((await regionStats(stored.bytes, landing, dusk)).every((s) => s.ok)).toBe(true);
  });

  it("normalises a backend's size to the canonical canvas and stores webp", async () => {
    const r = fakeRenderer([() => solid("#101014", { w: 1920, h: 1072 })]);
    const h = harness(demo, services, { renderers: [r], validator: sharpValidator() });
    await h.hello();
    const stored = (await h.engine.cache.getAsset(h.render().layers[0]!.url.slice(3)))!;
    expect(stored.mime).toBe("image/webp");
    expect(await sharp(stored.bytes).metadata()).toMatchObject({ width: 1920, height: 1080 });
  });
});

describe("budgets and fallback (spec §7.5)", () => {
  it("sends a flat render when the first scene misses its budget, then patches in the generated one", async () => {
    const r = fakeRenderer([() => solid("#101014")], { delayMs: 300 });
    const h = harness(demo, services, { renderers: [r], validator: sharpValidator(), budgets: { firstRenderMs: 50 } });
    await h.hello();
    const first = h.render();
    expect(first.fallback).toBe(true);
    const flatUrl = first.layers[0]!.url;
    await settle(500);
    const patch = h.sent.find((m): m is Extract<ServerMessage, { t: "patch" }> => m.t === "patch" && !!m.layers);
    expect(patch).toMatchObject({ render: first.seq, fallback: false });
    expect(patch!.layers![0]!.url).not.toBe(flatUrl);
  });

  it("falls back to flat when the backend fails, and keeps going", async () => {
    const r = fakeRenderer([() => solid("#101014")], { fail: true });
    const h = harness(demo, services, { renderers: [r], validator: sharpValidator() });
    await h.hello();
    expect(h.render().fallback).toBe(true);
    await h.press("signin");
    expect(h.render().head).toEqual({ tape: "login", frame: "form" });
    expect(h.log.lines.some((l) => l.msg === "generation failed; using flat")).toBe(true);
  });

  it("uses flat when the preferred renderer is unavailable", async () => {
    const r = { ...fakeRenderer([() => solid("#101014")]), available: () => false };
    const h = harness(demo, services, { renderers: [r], validator: sharpValidator() });
    await h.hello();
    expect(r.calls()).toBe(0);
    expect(h.render().fallback).toBe(false);
    expect(types(h.take())).toContain("render");
  });
});

describe("cache", () => {
  async function walk(h: ReturnType<typeof harness>) {
    await h.hello();
    await h.press("signin");
    await h.press("submit", { username: "ada", password: "lovelace" });
    await h.press("report");
    await h.press("backlink");
    await h.press("settings");
  }

  it("serves a second session at least 90 % from the cache (M2 exit)", async () => {
    const r = fakeRenderer([() => solid("#101014")]);
    const cache = new MemoryCache();
    const h1 = harness(demo, services, { renderers: [r], validator: sharpValidator(), cache });
    await walk(h1);
    await settle(300); // let prefetches land
    const callsAfterFirst = r.calls();
    const before = { ...h1.engine.host.stats };

    const h2 = harness(demo, services, { renderers: [r], validator: sharpValidator(), cache });
    await walk(h2);
    const s = h2.engine.host.stats;
    expect(r.calls()).toBe(callsAfterFirst);
    expect(s.hits / (s.hits + s.misses)).toBeGreaterThanOrEqual(0.9);
    expect(before.misses).toBeGreaterThan(0);
  });

  it("keeps re-rolls side by side in the manifest", async () => {
    const r = fakeRenderer([() => solid("#101014")]);
    const h = harness(demo, services, { renderers: [r], validator: sharpValidator(), debug: true });
    await h.hello();
    const k1 = h.render().key;
    await h.send({ t: "reroll" });
    const k2 = h.render().key;
    expect(k2).not.toBe(k1);
    expect(r.seedsFor(k1)).toEqual([dusk.seed]);
    expect(r.seedsFor(k2)).toEqual([dusk.seed + 1]);
    expect(await h.engine.cache.entries(k1)).toHaveLength(1);
    expect(await h.engine.cache.entries(k2)).toHaveLength(1);
  });

  it("refuses reroll outside debug", async () => {
    const r = fakeRenderer([() => solid("#101014")]);
    const h = harness(demo, services, { renderers: [r], validator: sharpValidator() });
    await h.hello();
    await settle(200);
    const calls = r.calls();
    h.take();
    await h.send({ t: "reroll" });
    expect(h.take()).toEqual([]);
    expect(r.calls()).toBe(calls);
  });
});

describe("ahead-of-time rendering", () => {
  it("fills the cache so a later session generates nothing", async () => {
    const r = fakeRenderer([() => solid("#101014")]);
    const cache = new MemoryCache();
    const aot = harness(demo, services, { renderers: [r], validator: sharpValidator(), cache });
    const results = await renderAhead(aot.engine, { viewports: ["desktop"], samples: [{}, { user: { plan: "pro" } }] });
    expect(results.filter((x) => x.node === "dashboard/home").map((x) => x.flavour).sort()).toEqual(['{"mood":"cool"}', '{"mood":"warm"}']);
    expect(results.every((x) => x.renderer === "fake-gen" && !x.fallback)).toBe(true);
    const generated = r.calls();

    const h = harness(demo, services, { renderers: [r], validator: sharpValidator(), cache });
    await h.hello();
    await h.press("signin");
    await h.press("submit", { username: "ada", password: "lovelace" });
    await h.press("report");
    await settle(200);
    expect(r.calls()).toBe(generated);
    expect(h.engine.host.stats.misses).toBe(0);
  });
});
