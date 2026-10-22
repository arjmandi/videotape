// The start of M2, against fakes: region validation, re-roll and patching,
// budgets with flat fallback, cache hit rate, and ahead-of-time rendering.
import sharp from "sharp";
import { describe, expect, it } from "vitest";
import {
  type SceneAsset, type SceneRenderer, type SceneRequest, type ServerMessage, button, dusk, frame, input, layout, sceneSvg, text,
} from "@videotape/core";
import demo from "../../../apps/site/tapes";
import { services } from "../../../apps/site/services";
import { MemoryCache, type Validator, contactSheet, drawingStructure, patchRegions, regionStats, renderAhead, sharpValidator } from "../src";
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
    expect(stats.filter((s) => s.mask === "reserved").every((s) => !s.ok && s.spread! > 24)).toBe(true);
  });

  it("fails a mid-grey field on contrast with the light foreground", async () => {
    const stats = await regionStats(await solid("#8a8a8a"), wf, dusk);
    expect(stats.filter((s) => s.mask === "reserved").every((s) => !s.ok && s.spread === 0 && s.contrast! < 4.5)).toBe(true);
  });

  it("checks reserved regions for calm and contrast, and surfaces and panels for lettering only", async () => {
    const stats = await regionStats(await solid("#101014"), wf, dusk);
    expect(stats.map((s) => `${s.id}:${s.mask}`).sort()).toEqual(["__panel:surface", "go:surface", "title:reserved", "user:reserved"]);
    expect(stats.find((s) => s.id === "go")).not.toHaveProperty("spread");
  });

  it("fails a small object behind a few words, which spread over the whole region misses", async () => {
    // A soft glow, and a small dark object straddling the left end of the title, as fal painted on v4.
    const { w, h } = wf.canvas;
    const [x, y, rw, rh] = wf.regions.find((r) => r.id === "title")!.rect;
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">` +
      `<defs><radialGradient id="g" cx="0.5" cy="0.45" r="0.6"><stop offset="0" stop-color="#b0582e"/><stop offset="1" stop-color="#16121a"/></radialGradient></defs>` +
      `<rect width="${w}" height="${h}" fill="url(#g)"/>` +
      `<rect x="${(x + rw * 0.05) * w}" y="${(y + rh * 0.1) * h}" width="${rw * 0.12 * w}" height="${rh * 0.8 * h}" rx="6" fill="#0b0a0d"/></svg>`;
    const stats = await regionStats(new Uint8Array(await sharp(Buffer.from(svg)).png().toBuffer()), wf, dusk, { lettering: false });
    const title = stats.find((s) => s.id === "title")!;
    expect(title.spread!).toBeLessThan(24);
    expect(title.tileSpread!).toBeGreaterThan(30);
    expect(title).toMatchObject({ ok: false, why: ["busy"] });
    expect(stats.find((s) => s.id === "user")!.ok).toBe(true);
  });

  it("finds fake lettering that spread and contrast miss, in text regions and on panels", async () => {
    // Faint grey words on a dark field, like the fake fields fal painted on the first live run.
    const { w, h } = wf.canvas;
    const at = (id: string) => wf.regions.find((r) => r.id === id)!.rect;
    const word = (id: string, text: string) => {
      const [x, y, , rh] = at(id);
      return `<text x="${(x + 0.01) * w}" y="${(y + rh * 0.75) * h}" font-family="Helvetica, Arial, sans-serif" font-size="${rh * h * 0.55}" fill="#6e6a74">${text}</text>`;
    };
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}"><rect width="${w}" height="${h}" fill="#1c1a22"/>` +
      `${word("user", "SUCCLATIONEL")}${word("go", "SIGN UP NOW")}</svg>`;
    const stats = await regionStats(new Uint8Array(await sharp(Buffer.from(svg)).png().toBuffer()), wf, dusk);
    const user = stats.find((s) => s.id === "user")!;
    expect(user).toMatchObject({ ok: false, why: ["lettering"] });
    expect(user.spread!).toBeLessThan(24); // the old checks alone would have passed it
    expect(user.text).toContain("SUCCLATIONEL");
    expect(stats.find((s) => s.id === "go")).toMatchObject({ mask: "surface", ok: false, why: ["lettering"] });
    expect(stats.find((s) => s.id === "title")!.ok).toBe(true);
  });

  it("passes every flat scene of the demo, lettering included", async () => {
    const h = harness(demo, services);
    for (const t of demo.tapes) {
      for (const f of t.frames) {
        for (const cls of ["phone", "desktop"] as const) {
          const plan = h.engine.plan({ tape: t.id, frame: f.id }, {}, cls);
          const flat = await h.engine.host.drawFlat(plan);
          const bytes = (await h.engine.cache.getAsset(flat.layer.url.slice(3)))!.bytes;
          const failing = (await regionStats(bytes, plan.wireframe, dusk)).filter((s) => !s.ok);
          expect(failing, `${t.id}/${f.id} ${cls}`).toEqual([]);
        }
      }
    }
  }, 60_000);

  it("patches the failing regions only", async () => {
    const patched = await patchRegions(await noise(), wf, dusk, ["user"], "png");
    const after = (await regionStats(patched, wf, dusk)).filter((s) => s.mask === "reserved");
    expect(after.find((s) => s.id === "user")!.ok).toBe(true);
    expect(after.find((s) => s.id === "title")!.ok).toBe(false);
  });
});

describe("what generators are shown", () => {
  it("conditions on the scene drawing, not the wireframe with its text bars and controls", async () => {
    const seen: string[] = [];
    const r = { ...fakeRenderer([() => solid("#101014")]) };
    const render = r.render.bind(r);
    r.render = (req, signal) => (seen.push(req.condition.svg), render(req, signal));
    const h = harness(demo, services, { renderers: [r], validator: sharpValidator(), budgets: { firstRenderMs: 30_000 } });
    await h.hello();
    const plan = h.engine.plan({ tape: "landing", frame: "home" }, {}, "desktop");
    expect(seen[0]).toBe(plan.condition);
    expect(seen[0]).not.toBe(plan.wireframe.svg);
    // The primary button face and text bars are in the wireframe only.
    expect(plan.wireframe.svg).toContain(dusk.palette.accent);
    expect(seen[0]).not.toMatch(new RegExp(`<rect[^>]*fill="${dusk.palette.accent}"`));
  });

  it("gives extra freedom only to frames whose drawing has nothing to build on", async () => {
    const seen: Array<number | undefined> = [];
    const r = { ...fakeRenderer([() => solid("#101014")]) };
    const render = r.render.bind(r);
    r.render = (req, signal) => (seen.push(req.freedom), render(req, signal));
    const h = harness(demo, services, { renderers: [r], validator: sharpValidator(), budgets: { firstRenderMs: 30_000 } });
    const landing = h.engine.plan({ tape: "landing", frame: "home" }, {}, "desktop");
    const login = h.engine.plan({ tape: "login", frame: "form" }, {}, "desktop");
    expect(drawingStructure(landing.wireframe)).toBe(0);
    expect(landing.freedom).toBe(0.95);
    expect(login.freedom).toBeUndefined();
    await h.hello();
    expect(seen[0]).toBe(0.95);

    // Freedom is part of the key when set, and only then.
    const off = harness(demo, services, { renderers: [r], emptyFreedom: false });
    const landingOff = off.engine.plan({ tape: "landing", frame: "home" }, {}, "desktop");
    expect(landingOff.freedom).toBeUndefined();
    expect(h.engine.host.keyFor(r, landing)).not.toBe(off.engine.host.keyFor(r, landingOff));
    expect(h.engine.host.keyFor(r, login)).toBe(off.engine.host.keyFor(r, off.engine.plan({ tape: "login", frame: "form" }, {}, "desktop")));
  });

  it("steers the subject into the free space when the drawing is empty, and only then", async () => {
    const h = harness(demo, services);
    const landing = h.engine.plan({ tape: "landing", frame: "home" }, {}, "desktop");
    const login = h.engine.plan({ tape: "login", frame: "form" }, {}, "desktop");
    expect(landing.prompt).toContain("the main subject placed in the upper part of the frame, across its width, nothing in the middle band of the frame");
    expect(landing.condition).not.toBe(sceneSvg(landing.wireframe.regions, landing.wireframe.canvas, dusk));
    expect(login.prompt).not.toContain("main subject");
    expect(login.condition).toBe(sceneSvg(login.wireframe.regions, login.wireframe.canvas, dusk));
  });

  it("starts a fresh cache key when the style's prompt changes", async () => {
    const r = fakeRenderer([() => solid("#101014")]);
    const plain = harness(demo, services, { renderers: [r] });
    const plan = plain.engine.plan({ tape: "landing", frame: "home" }, {}, "desktop");
    const edited = { ...plan, style: { ...plan.style, prompt: { ...plan.style.prompt, prefix: "Watercolour backdrop, " } } };
    expect(plain.engine.host.keyFor(r, edited)).not.toBe(plain.engine.host.keyFor(r, plan));
    // The flat renderer ignores the prompt, so its key does not move with it.
    const flat = plain.engine.host.flat;
    expect(plain.engine.host.keyFor(flat, { ...plan, prompt: "anything" })).toBe(plain.engine.host.keyFor(flat, plan));
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
    expect(dbg.patched.filter((id) => !["docs"].includes(id)).sort()).toEqual(["headline", "signin", "sub", "wordmark", "github"].sort());
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
    const isLayerPatch = (m: ServerMessage): m is Extract<ServerMessage, { t: "patch" }> => m.t === "patch" && !!m.layers;
    for (let waited = 0; !h.sent.some(isLayerPatch) && waited < 10_000; waited += 50) await settle(50);
    const patch = h.sent.find(isLayerPatch);
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

  it("never calls the backend in cache-only mode, but serves what is cached", async () => {
    const r = fakeRenderer([() => solid("#101014")]);
    const cache = new MemoryCache();
    const warm = harness(demo, services, { renderers: [r], validator: sharpValidator(), cache });
    await renderAhead(warm.engine, { viewports: ["desktop"], frames: ["landing"] });
    const calls = r.calls();
    const h = harness(demo, services, { renderers: [r], validator: sharpValidator(), cache, generate: false, debug: true });
    await h.hello();
    expect(h.render()).toMatchObject({ fallback: false, debug: { renderer: "fake-gen", cache: "hit" } });
    await h.press("signin");
    await settle(200);
    expect(h.render()).toMatchObject({ fallback: true, debug: { renderer: "flat" } });
    expect(r.calls()).toBe(calls);
  });

  it("reports flat as a fallback in ahead-of-time results when the generator is unavailable", async () => {
    const r = { ...fakeRenderer([() => solid("#101014")]), available: () => false };
    const h = harness(demo, services, { renderers: [r] });
    const [res] = await renderAhead(h.engine, { viewports: ["desktop"], frames: ["landing"] });
    expect(res).toMatchObject({ renderer: "flat", fallback: true });
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

describe("re-checking cached scenes", () => {
  /** A validator from before the current checks: passes everything, stamps an old version. */
  const lenient = (): Validator => ({ version: "1", check: async () => ({ failing: [] }), patch: async (a) => a });

  it("checks a scene cached under an older validator once, and patches what now fails, without generating", async () => {
    const r = fakeRenderer([() => noise(5)]);
    const cache = new MemoryCache();
    const old = harness(demo, services, { renderers: [r], validator: lenient(), cache });
    await renderAhead(old.engine, { viewports: ["desktop"], frames: ["landing"] });
    const calls = r.calls();
    const key = old.engine.host.keyFor(r, old.engine.plan({ tape: "landing", frame: "home" }, {}, "desktop"));
    const stale = (await cache.lookup(key))!;

    let checks = 0;
    const current = sharpValidator();
    const counting: Validator = { ...current, check: (...a) => (checks++, current.check(...a)) };
    const h = harness(demo, services, { renderers: [r], validator: counting, cache, generate: false, budgets: { firstRenderMs: 30_000 } });
    await h.hello();
    expect(r.calls()).toBe(calls);
    expect(h.render().fallback).toBe(false);
    expect(h.render().layers[0]!.url).not.toBe(`/a/${stale.file}`);
    const now = (await cache.lookup(key))!;
    expect(now.meta).toMatchObject({ validator: current.version, rechecked: { from: stale.file } });
    expect((now.meta!.rechecked as { failing: string[] }).failing.length).toBeGreaterThan(0);

    const before = checks;
    const again = harness(demo, services, { renderers: [r], validator: counting, cache, generate: false });
    await again.hello();
    expect(checks).toBe(before);
  });

  it("leaves a pinned scene alone", async () => {
    const r = fakeRenderer([() => noise(5)]);
    const cache = new MemoryCache();
    const old = harness(demo, services, { renderers: [r], validator: lenient(), cache });
    await renderAhead(old.engine, { viewports: ["desktop"], frames: ["landing"] });
    const key = old.engine.host.keyFor(r, old.engine.plan({ tape: "landing", frame: "home" }, {}, "desktop"));
    const entry = (await cache.lookup(key))!;
    await cache.record(key, { ...entry, pinned: true });
    const h = harness(demo, services, { renderers: [r], validator: sharpValidator(), cache, generate: false });
    await h.hello();
    expect(h.render().layers[0]!.url).toBe(`/a/${entry.file}`);
  });
});

describe("ahead-of-time rendering", () => {
  it("renders only the frames asked for, and records every attempt with its region numbers", async () => {
    const r = fakeRenderer([() => noise(3), () => solid("#101014")]);
    const aot = harness(demo, services, { renderers: [r], validator: sharpValidator() });
    const results = await renderAhead(aot.engine, { viewports: ["desktop"], frames: ["landing", "login/form"] });
    expect(results.map((x) => x.node)).toEqual(["landing/home", "login/form"]);
    const landing = results[0]!;
    expect(landing.attempts!.map((a) => [a.seed, a.failing.length > 0])).toEqual([[dusk.seed, true], [dusk.seed + 1, false]]);
    expect(landing.attempts![0]!.regions!.find((x) => x.id === "headline")).toMatchObject({ ok: false });
    expect(await aot.engine.cache.getAsset(landing.attempts![0]!.file)).toBeDefined();
    expect(landing.prompt).toContain("cassette tape");

    // A cache hit reports how the scene was made.
    const again = await renderAhead(aot.engine, { viewports: ["desktop"], frames: ["landing"] });
    expect(again[0]).toMatchObject({ cache: "hit", rerolls: 1 });
    expect(again[0]!.attempts).toHaveLength(2);

    const wfLanding = aot.engine.plan({ tape: "landing", frame: "home" }, {}, "desktop").wireframe;
    const png = await contactSheet(landing.attempts!.map((a) => ({ title: "t", subtitle: "s", file: a.file, wireframe: wfLanding, regions: a.regions! })), aot.engine.cache);
    expect(await sharp(png).metadata()).toMatchObject({ format: "png", height: 20 + 360 + 54 + 20 });
  });

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
