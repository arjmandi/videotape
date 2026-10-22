// videotape render: ahead-of-time render into the cache (spec §11).

import { join } from "node:path";
import { VIEWPORT_CLASSES, type ViewportClass } from "@videotape/core";
import { Engine, FsCache, consoleLogger, renderAhead } from "@videotape/engine";
import { loadProject } from "./load";
import { resolveRenderers } from "./renderers";

export async function runRender(dir: string, opts: { renderers?: string | undefined; viewports?: string | undefined }): Promise<number> {
  const { dir: root, config } = await loadProject(dir);
  const logger = consoleLogger("warn");
  const viewports = (opts.viewports?.split(",") ?? [...VIEWPORT_CLASSES]).map((v) => v.trim()) as ViewportClass[];
  const bad = viewports.filter((v) => !VIEWPORT_CLASSES.includes(v));
  if (bad.length) throw new Error(`unknown viewport class ${bad.join(", ")} (${VIEWPORT_CLASSES.join(", ")})`);
  const renderers = await resolveRenderers(opts.renderers?.split(",") ?? config.renderers ?? ["flat"], config.rendererOptions ?? {}, logger);
  const engine = new Engine(config, {
    cache: new FsCache(join(root, config.cache ?? ".videotape/cache")),
    logger,
    renderers: renderers.scene,
    ...(renderers.validator ? { validator: renderers.validator } : {}),
  });
  process.stdout.write(`rendering with ${renderers.scene.map((r) => r.id).join(" → ")} at ${viewports.join(", ")}\n`);
  const results = await renderAhead(engine, {
    viewports,
    ...(config.aheadSamples ? { samples: config.aheadSamples } : {}),
    onScene: (r) => process.stdout.write(
      `  ${r.cache === "hit" ? "·" : "✚"} ${r.node.padEnd(18)} ${r.viewportClass.padEnd(7)} ${r.renderer.padEnd(10)} ${String(r.ms).padStart(6)} ms` +
      `${r.fallback ? "  FALLBACK" : ""}${r.rerolls ? `  rerolls ${r.rerolls}` : ""}${r.patched ? `  patched ${r.patched.join(",")}` : ""}` +
      `${r.flavour !== "{}" ? `  ${r.flavour}` : ""}\n`),
  });
  const misses = results.filter((r) => r.cache === "miss").length;
  const fallbacks = results.filter((r) => r.fallback).length;
  process.stdout.write(`${results.length} scenes: ${misses} rendered, ${results.length - misses} already cached${fallbacks ? `, ${fallbacks} fell back to flat` : ""}\n`);
  return fallbacks ? 1 : 0;
}
