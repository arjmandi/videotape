// videotape render: ahead-of-time render into the cache (spec §11).

import { writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { VIEWPORT_CLASSES, type ViewportClass } from "@videotape/core";
import { type AheadResult, Engine, FsCache, type SheetTile, consoleLogger, contactSheet, regionStats, renderAhead } from "@videotape/engine";
import { loadProject } from "./load";
import { resolveRenderers } from "./renderers";

export interface RenderOptions {
  renderers?: string | undefined;
  viewports?: string | undefined;
  frames?: string | undefined;
  sheet?: string | undefined;
  cacheOnly?: boolean | undefined;
}

const list = (s: string | undefined) => s?.split(",").map((x) => x.trim()).filter(Boolean);

function line(r: AheadResult): string {
  const head =
    `  ${r.fallback ? "✗" : r.cache === "hit" ? "·" : "✚"} ${r.node.padEnd(18)} ${r.viewportClass.padEnd(7)} ${r.renderer.padEnd(10)} ${String(r.ms).padStart(6)} ms` +
    `${r.fallback ? "  FALLBACK" : ""}${r.rerolls ? `  rerolls ${r.rerolls}` : ""}${r.patched ? `  patched ${r.patched.join(",")}` : ""}` +
    `${r.flavour !== "{}" ? `  ${r.flavour}` : ""}`;
  const tries = (r.attempts ?? []).map((a, i) => {
    const why = (id: string) => {
      const c = a.regions?.find((x) => x.id === id);
      return c?.why ? ` (${c.why.join("+")}${c.text ? `: "${c.text}"` : ""})` : "";
    };
    return `      attempt ${i + 1} seed ${a.seed}: ${a.failing.length ? `failed ${a.failing.map((id) => id + why(id)).join(", ")}` : "passed"}`;
  });
  const recheck = r.rechecked
    ? [`      re-checked under the current validator: ${r.rechecked.failing.length ? `failed ${r.rechecked.failing.join(", ")}, patched` : "passed"}`]
    : [];
  return [head, ...tries, ...recheck].join("\n") + "\n";
}

export async function runRender(dir: string, opts: RenderOptions): Promise<number> {
  const { dir: root, config } = await loadProject(dir);
  const logger = consoleLogger("warn");
  const viewports = (list(opts.viewports) ?? [...VIEWPORT_CLASSES]) as ViewportClass[];
  const bad = viewports.filter((v) => !VIEWPORT_CLASSES.includes(v));
  if (bad.length) throw new Error(`unknown viewport class ${bad.join(", ")} (${VIEWPORT_CLASSES.join(", ")})`);
  const frames = list(opts.frames);
  const renderers = await resolveRenderers(list(opts.renderers) ?? config.renderers ?? ["flat"], config.rendererOptions ?? {}, logger);
  const engine = new Engine(config, {
    cache: new FsCache(join(root, config.cache ?? ".videotape/cache")),
    logger,
    renderers: renderers.scene,
    ...(renderers.validator ? { validator: renderers.validator } : {}),
    ...(opts.cacheOnly ? { generate: false } : {}),
  });
  if (frames) {
    const known = new Set(config.app.tapes.flatMap((t) => [t.id, ...t.frames.map((f) => `${t.id}/${f.id}`)]));
    const unknown = frames.filter((f) => !known.has(f));
    if (unknown.length) throw new Error(`unknown frame or tape ${unknown.join(", ")}`);
  }
  process.stdout.write(`rendering with ${renderers.scene.map((r) => r.id).join(" → ")} at ${viewports.join(", ")}\n`);
  const results = await renderAhead(engine, {
    viewports,
    ...(frames ? { frames } : {}),
    ...(config.aheadSamples ? { samples: config.aheadSamples } : {}),
    onScene: (r) => process.stdout.write(line(r)),
  });
  const fallbacks = results.filter((r) => r.fallback).length;
  const rendered = results.filter((r) => !r.fallback && r.cache === "miss").length;
  const cached = results.length - fallbacks - rendered;
  process.stdout.write(`${results.length} scenes: ${rendered} rendered, ${cached} already cached${fallbacks ? `, ${fallbacks} fell back to flat` : ""}\n`);

  if (opts.sheet) {
    const tiles: SheetTile[] = [];
    for (const r of results) {
      const [tape, frame] = r.node.split("/") as [string, string];
      const plan = engine.plan({ tape, frame }, {}, r.viewportClass);
      const title = `${r.node} · ${r.viewportClass}`;
      const mood = Object.values(JSON.parse(r.flavour) as Record<string, unknown>).join(" ");
      const tag = mood ? `${mood} · ` : "";
      for (const [i, a] of (r.attempts ?? []).entries()) {
        if (r.attempts!.length === 1 && !a.failing.length) break; // the served tile shows it
        tiles.push({ title, subtitle: `${tag}try ${i + 1}, seed ${a.seed}: ${a.failing.length ? `failed ${a.failing.join(", ")}` : "passed"}`,
          file: a.file, wireframe: plan.wireframe, ...(a.regions ? { regions: a.regions } : {}) });
      }
      const file = r.url.replace(/^\/a\//, "");
      const asset = await engine.cache.getAsset(file);
      const regions = asset ? await regionStats(asset.bytes, plan.wireframe, plan.style) : undefined;
      tiles.push({ title, subtitle: `${tag}served: ${r.renderer}${r.rerolls ? `, ${r.rerolls} re-rolls` : ""}${r.patched ? `, patched ${r.patched.join(", ")}` : ""}`,
        file, wireframe: plan.wireframe, ...(regions ? { regions } : {}), ...(r.patched ? { patched: r.patched } : {}) });
    }
    const out = resolve(opts.sheet);
    writeFileSync(out, await contactSheet(tiles, engine.cache));
    process.stdout.write(`contact sheet: ${out}\n`);
  }
  return fallbacks ? 1 : 0;
}
