// Ahead-of-time rendering (spec §11, `videotape render`): fill the cache for
// every frame × viewport class before anyone visits. Scenes depend on flavour,
// and flavour on reel data, so callers pass data samples that cover the
// flavours they care about; the default sample is an empty store.

import { type Data, VIEWPORT_CLASSES, type ViewportClass } from "@videotape/core";
import type { Engine } from "./engine";

export interface AheadResult {
  node: string;
  viewportClass: ViewportClass;
  flavour: string;
  renderer: string;
  cache: "hit" | "miss";
  fallback: boolean;
  ms: number;
  rerolls?: number;
  patched?: string[];
}

export interface AheadOptions {
  viewports?: ViewportClass[];
  samples?: Data[];
  onScene?(r: AheadResult): void;
}

export async function renderAhead(engine: Engine, opts: AheadOptions = {}): Promise<AheadResult[]> {
  const out: AheadResult[] = [];
  const seen = new Set<string>();
  for (const tape of engine.app.tapes) {
    for (const frame of tape.frames) {
      for (const cls of opts.viewports ?? [...VIEWPORT_CLASSES]) {
        for (const data of opts.samples ?? [{}]) {
          const plan = engine.plan({ tape: tape.id, frame: frame.id }, data, cls);
          const flavour = JSON.stringify(plan.flavour);
          const id = `${plan.node}|${cls}|${flavour}`;
          if (seen.has(id)) continue;
          seen.add(id);
          const t0 = performance.now();
          const scene = await engine.host.scene(plan);
          const r: AheadResult = {
            node: plan.node, viewportClass: cls, flavour, renderer: scene.renderer, cache: scene.cache, fallback: scene.fallback,
            ms: Math.round(performance.now() - t0),
            ...(scene.rerolls !== undefined ? { rerolls: scene.rerolls } : {}),
            ...(scene.patched?.length ? { patched: scene.patched } : {}),
          };
          out.push(r);
          opts.onScene?.(r);
        }
      }
    }
  }
  return out;
}
