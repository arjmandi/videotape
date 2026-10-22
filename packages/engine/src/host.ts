// The renderer host (spec §7.1, §7.3, §7.5): cache first, then generate with
// the preferred renderer inside a budget, validate and re-roll, and fall back
// to the flat renderer. The flat renderer is always the last resort.

import type { Flavour, Layer, SceneAsset, SceneRenderer, SceneRequest, StylePack, Wireframe } from "@videotape/core";
import { rasterize } from "@videotape/renderer-flat";
import type { Cache, ManifestEntry } from "./cache";
import { assetUrl } from "./cache";
import { sceneKey } from "./keys";
import type { Logger } from "./log";

export interface ScenePlan {
  /** `tape/frame`, for logs and the HUD. */
  node: string;
  frameHash: string;
  viewportClass: string;
  style: StylePack;
  seed: number;
  flavour: Flavour;
  wireframe: Wireframe;
  prompt: string;
  /**
   * The conditioning image's source: the scene drawing (panels and media frames on the
   * palette gradient), not the full wireframe. Text bars, field strips, and button shapes
   * read as a UI mock-up, and image models then paint fake controls and lettering.
   */
  condition: string;
  /** Extra latitude for drawings with almost nothing to build on (no panels, no media frames). */
  freedom?: number;
}

export interface SceneResult {
  key: string;
  layer: Layer;
  renderer: string;
  cache: "hit" | "miss";
  /** True when a flat render stands in for a generated one that missed its budget or failed. */
  fallback: boolean;
  /** When `fallback` is set: resolves with the generated scene once it lands. */
  pending?: Promise<SceneResult | undefined>;
  rerolls?: number;
  patched?: string[];
  /** Every generation attempt for this key, kept for review. */
  attempts?: Attempt[];
  /** Set when a cached scene was checked again under a newer validator. */
  rechecked?: { failing: string[] };
}

/** One generation attempt: its seed, the raw output as stored, and what failed. */
export interface Attempt {
  seed: number;
  file: string;
  failing: string[];
  regions?: RegionCheck[];
}

export interface RegionCheck {
  id: string;
  /** reserved: must be calm, readable, and free of lettering. surface: free of lettering. */
  mask: "reserved" | "surface";
  /** Standard deviation of luma, 0–255, over the whole region (reserved only). */
  spread?: number;
  /** The same, in the region's worst tile (reserved only). */
  tileSpread?: number;
  /** Contrast of the region's mean colour against the style's foreground, 1–21 (reserved only). */
  contrast?: number;
  /** Words OCR read inside the region; anything above zero fails it. */
  words: number;
  /** What it read, for people reviewing the scene. */
  text?: string;
  ok: boolean;
  /** Why it failed: busy, contrast, lettering. */
  why?: string[];
}

/** Region checks for generated scenes (spec §7.3). See ./validate. */
export interface Validator {
  /** Changes when a check changes; cached generated scenes made under another version are checked again. */
  version?: string;
  /** Brings a backend's output to the canonical canvas size and the stored format. */
  normalize?(asset: SceneAsset, wf: Wireframe): Promise<SceneAsset>;
  check(asset: SceneAsset, wf: Wireframe, style: StylePack): Promise<{ failing: string[]; regions?: RegionCheck[] }>;
  patch(asset: SceneAsset, wf: Wireframe, style: StylePack, failing: string[]): Promise<SceneAsset>;
}

export interface HostOptions {
  cache: Cache;
  logger: Logger;
  validator?: Validator;
  /** Re-rolls after the first attempt fails validation (spec §7.3: three). */
  maxRerolls?: number;
  /** Hard cap on one generation call. */
  generateTimeoutMs?: number;
  /** False serves cached generated scenes only and never calls a generative backend. Default true. */
  generate?: boolean;
}

/** Counters for the HUD and for the cache hit-rate test. */
export interface HostStats {
  hits: number;
  misses: number;
  generated: number;
  fallbacks: number;
  rerolls: number;
  patched: number;
}

const sleep = (ms: number) => new Promise<"timeout">((r) => setTimeout(() => r("timeout"), ms).unref?.());

export class RendererHost {
  readonly flat: SceneRenderer;
  readonly stats: HostStats = { hits: 0, misses: 0, generated: 0, fallbacks: 0, rerolls: 0, patched: 0 };
  private inflight = new Map<string, Promise<SceneResult>>();
  private rechecks = new Map<string, Promise<ManifestEntry>>();

  constructor(readonly renderers: SceneRenderer[], private opts: HostOptions) {
    const flat = renderers.find((r) => r.id === "flat");
    if (!flat) throw new Error("the flat renderer must be registered");
    this.flat = flat;
  }

  /** The renderer that should draw this scene: the first available one, flat last. */
  primary(): SceneRenderer {
    return this.renderers.find((r) => r.available?.() ?? true) ?? this.flat;
  }

  keyFor(r: SceneRenderer, plan: ScenePlan): string {
    return sceneKey({
      renderer: r, frameHash: plan.frameHash, viewportClass: plan.viewportClass, style: plan.style, seed: plan.seed, flavour: plan.flavour,
      condition: plan.condition, prompt: r.deterministic ? "" : plan.prompt,
      ...(plan.freedom !== undefined && !r.deterministic ? { freedom: plan.freedom } : {}),
    });
  }

  /**
   * Best scene within `budgetMs`. With no budget (ahead-of-time rendering),
   * waits for generation. Never throws: the flat renderer is the floor.
   */
  async scene(plan: ScenePlan, budgetMs?: number, opts: { quiet?: boolean } = {}): Promise<SceneResult> {
    const r = this.primary();
    // Prefetches are quiet: they warm the cache without counting towards hit or fallback rates.
    const count = (k: "hits" | "misses" | "fallbacks") => void (opts.quiet || this.stats[k]++);
    if (r === this.flat) return this.drawFlat(plan);
    const key = this.keyFor(r, plan);
    const hit = await this.opts.cache.lookup(key);
    if (hit) {
      count("hits");
      return this.result(key, await this.recheck(r, plan, key, hit), "hit");
    }
    count("misses");
    if (this.opts.generate === false) {
      count("fallbacks");
      return { ...(await this.drawFlat(plan)), fallback: true };
    }
    const gen = this.generate(r, plan, key);
    const safe = gen.catch((e: unknown) => {
      this.opts.logger.warn("generation failed; using flat", { node: plan.node, renderer: r.id, error: e instanceof Error ? e.message : String(e) });
      return undefined;
    });
    const won = budgetMs === undefined ? await safe : await Promise.race([safe, sleep(budgetMs)]);
    if (won && won !== "timeout") return won;
    count("fallbacks");
    const flat = await this.drawFlat(plan);
    return { ...flat, fallback: true, ...(won === "timeout" ? { pending: safe } : {}) };
  }

  /** Looks up or draws the flat scene. */
  async drawFlat(plan: ScenePlan): Promise<SceneResult> {
    const key = this.keyFor(this.flat, plan);
    const hit = await this.opts.cache.lookup(key);
    if (hit) return this.result(key, hit, "hit");
    return this.once(key, async () => {
      const asset = await this.flat.render(await this.request(key, plan, plan.seed, false), new AbortController().signal);
      const entry = await this.store(key, asset, this.flat.id, plan.seed);
      return this.result(key, entry, "miss");
    });
  }

  private generate(r: SceneRenderer, plan: ScenePlan, key: string): Promise<SceneResult> {
    return this.once(key, async () => {
      const max = this.opts.maxRerolls ?? 3;
      let asset: SceneAsset | undefined;
      let failing: string[] = [];
      const attempts: Attempt[] = [];
      let attempt = 0;
      for (; attempt <= max; attempt++) {
        const seed = plan.seed + attempt;
        const ac = new AbortController();
        const timer = setTimeout(() => ac.abort(new Error("generation timed out")), this.opts.generateTimeoutMs ?? 120_000);
        try {
          asset = await r.render(await this.request(key, plan, seed, true), ac.signal);
        } finally {
          clearTimeout(timer);
        }
        this.stats.generated++;
        if (!r.deterministic && this.opts.validator?.normalize) asset = await this.opts.validator.normalize(asset, plan.wireframe);
        if (r.deterministic || !this.opts.validator) break;
        const verdict = await this.opts.validator.check(asset, plan.wireframe, plan.style);
        failing = verdict.failing;
        // Keep each raw attempt (content-addressed, so cheap) so a person can see why it was re-rolled.
        const raw = await this.opts.cache.putAsset(asset.bytes, asset.mime);
        attempts.push({ seed, file: raw.file, failing, ...(verdict.regions ? { regions: verdict.regions } : {}) });
        if (failing.length === 0) break;
        this.opts.logger.info("scene failed region validation", { node: plan.node, attempt, failing: failing.join(",") });
        if (attempt < max) this.stats.rerolls++;
      }
      const rerolls = Math.min(attempt, max);
      if (failing.length && this.opts.validator && asset) {
        asset = await this.opts.validator.patch(asset, plan.wireframe, plan.style, failing);
        this.stats.patched++;
      }
      const meta = {
        rerolls, patched: failing, prompt: plan.prompt, ...(attempts.length ? { attempts } : {}),
        ...(this.opts.validator?.version && !r.deterministic ? { validator: this.opts.validator.version } : {}),
      };
      const entry = await this.store(key, asset!, r.id, plan.seed + rerolls, meta);
      return { ...this.result(key, entry, "miss"), rerolls, patched: failing, ...(attempts.length ? { attempts } : {}) };
    });
  }

  /**
   * A cached generated scene made under an older validator is checked again, once per key.
   * What fails now is patched with a flat fill, as after the last re-roll; nothing is
   * generated, so this costs no backend calls. Pinned entries are a person's choice and are kept.
   */
  private recheck(r: SceneRenderer, plan: ScenePlan, key: string, entry: ManifestEntry): Promise<ManifestEntry> {
    const v = this.opts.validator;
    if (r.deterministic || !v?.version || entry.pinned || entry.meta?.validator === v.version) return Promise.resolve(entry);
    let p = this.rechecks.get(key);
    if (!p) {
      p = this.runRecheck(v, plan, key, entry).catch((e: unknown) => {
        this.opts.logger.warn("re-checking a cached scene failed; serving it as is", { node: plan.node, error: e instanceof Error ? e.message : String(e) });
        return entry;
      });
      this.rechecks.set(key, p);
    }
    return p;
  }

  private async runRecheck(v: Validator, plan: ScenePlan, key: string, entry: ManifestEntry): Promise<ManifestEntry> {
    const stored = await this.opts.cache.getAsset(entry.file);
    if (!stored) return entry;
    const asset: SceneAsset = { key, mime: stored.mime as SceneAsset["mime"], bytes: stored.bytes, meta: {} };
    const verdict = await v.check(asset, plan.wireframe, plan.style);
    const before = Array.isArray(entry.meta?.patched) ? (entry.meta.patched as string[]) : [];
    let file = entry.file;
    if (verdict.failing.length) {
      const fixed = await v.patch(asset, plan.wireframe, plan.style, verdict.failing);
      file = (await this.opts.cache.putAsset(fixed.bytes, fixed.mime)).file;
      this.stats.patched++;
      this.opts.logger.info("cached scene fails a newer check; patched", { node: plan.node, failing: verdict.failing.join(",") });
    }
    const next: ManifestEntry = {
      ...entry,
      file,
      createdAt: new Date().toISOString(),
      meta: {
        ...entry.meta,
        validator: v.version,
        patched: [...new Set([...before, ...verdict.failing])],
        rechecked: { from: entry.file, failing: verdict.failing, ...(verdict.regions ? { regions: verdict.regions } : {}) },
      },
    };
    await this.opts.cache.record(key, next);
    return next;
  }

  private async once(key: string, fn: () => Promise<SceneResult>): Promise<SceneResult> {
    const running = this.inflight.get(key);
    if (running) return running;
    const p = fn().finally(() => this.inflight.delete(key));
    this.inflight.set(key, p);
    return p;
  }

  private async request(key: string, plan: ScenePlan, seed: number, generative: boolean): Promise<SceneRequest> {
    const wf = plan.wireframe;
    const empty = new Uint8Array();
    return {
      key,
      canvas: wf.canvas,
      seed,
      prompt: plan.prompt,
      ...(plan.style.prompt.negative ? { negative: plan.style.prompt.negative } : {}),
      // Rasterising the conditioning image and masks is wasted work for the flat renderer.
      condition: { svg: plan.condition, png: generative ? rasterize(plan.condition) : empty },
      masks: generative ? { reserved: maskPng(wf, "reserved"), surface: maskPng(wf, "surface") } : { reserved: empty, surface: empty },
      style: plan.style,
      wireframe: wf,
      ...(plan.freedom !== undefined ? { freedom: plan.freedom } : {}),
    };
  }

  private async store(key: string, asset: SceneAsset, renderer: string, seed: number, meta?: Record<string, unknown>): Promise<ManifestEntry> {
    const ref = await this.opts.cache.putAsset(asset.bytes, asset.mime);
    const entry: ManifestEntry = { file: ref.file, renderer, seed, createdAt: new Date().toISOString(), ...(meta ? { meta } : {}) };
    await this.opts.cache.record(key, entry);
    return entry;
  }

  private result(key: string, entry: ManifestEntry, cache: "hit" | "miss"): SceneResult {
    const out: SceneResult = { key, layer: { kind: "image", url: assetUrl(entry.file), z: 0 }, renderer: entry.renderer, cache, fallback: false };
    // A cache hit still reports how the scene was made, for the HUD and for `videotape render`.
    const m = entry.meta;
    if (typeof m?.rerolls === "number") out.rerolls = m.rerolls;
    if (Array.isArray(m?.patched) && m.patched.length) out.patched = m.patched as string[];
    if (Array.isArray(m?.attempts)) out.attempts = m.attempts as Attempt[];
    const rc = m?.rechecked as { failing?: string[] } | undefined;
    if (rc && Array.isArray(rc.failing)) out.rechecked = { failing: rc.failing };
    return out;
  }
}

/** White where the mask applies, black elsewhere, at canvas size. */
export function maskPng(wf: Wireframe, mask: "reserved" | "surface"): Uint8Array {
  const { w, h } = wf.canvas;
  const rects = wf.regions
    .filter((r) => r.mask === mask)
    .map((r) => `<rect x="${r.rect[0] * w}" y="${r.rect[1] * h}" width="${r.rect[2] * w}" height="${r.rect[3] * h}" fill="#fff"/>`)
    .join("");
  return rasterize(`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}"><rect width="${w}" height="${h}" fill="#000"/>${rects}</svg>`);
}
