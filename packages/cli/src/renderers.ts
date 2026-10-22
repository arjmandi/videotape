// Renderer ids in config and flags → instances. Vendor renderers are imported
// only when named, so an app that never uses one never loads it.

import type { SceneRenderer } from "@videotape/core";
import type { Logger, Validator } from "@videotape/engine";
import { flatRenderer } from "@videotape/renderer-flat";

type Factory = (opts: Record<string, unknown>) => Promise<SceneRenderer>;

const FACTORIES: Record<string, Factory> = {
  flat: async () => flatRenderer(),
};

export const KNOWN_RENDERERS = Object.keys(FACTORIES);

export async function resolveRenderers(
  wanted: Array<SceneRenderer | string>,
  options: Record<string, Record<string, unknown>>,
  logger: Logger,
): Promise<{ scene: SceneRenderer[]; validator?: Validator }> {
  const scene: SceneRenderer[] = [];
  for (const w of wanted) {
    if (typeof w !== "string") {
      scene.push(w);
      continue;
    }
    const id = w.trim();
    const make = FACTORIES[id];
    if (!make) throw new Error(`unknown renderer "${id}" (known: ${KNOWN_RENDERERS.join(", ")})`);
    const r = await make(options[id] ?? {});
    if (r.available?.() === false) logger.warn(`renderer ${id} is unavailable; scenes fall back to flat`);
    scene.push(r);
  }
  if (!scene.some((r) => r.id === "flat")) scene.push(flatRenderer());
  return { scene };
}
