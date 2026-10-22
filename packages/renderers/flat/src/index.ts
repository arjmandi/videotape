// The flat renderer (spec §7.7): rasterises the frame's scene drawing with the
// style palette. It is the reference renderer, used in CI and as every fallback,
// so it must be deterministic: same request, same bytes.

import { Resvg } from "@resvg/resvg-js";
import { type SceneAsset, type SceneRenderer, type SceneRequest, sceneSvg } from "@videotape/core";

/** SVG → PNG at the SVG's own size. No fonts are loaded; wireframes contain no text. */
export function rasterize(svg: string, width?: number): Uint8Array {
  const r = new Resvg(svg, {
    font: { loadSystemFonts: false },
    ...(width ? { fitTo: { mode: "width" as const, value: width } } : {}),
  });
  return new Uint8Array(r.render().asPng());
}

export function flatRenderer(): SceneRenderer {
  return {
    id: "flat",
    version: "3",
    kind: "scene",
    deterministic: true,
    async render(req: SceneRequest, signal: AbortSignal): Promise<SceneAsset> {
      signal.throwIfAborted();
      // The flat picture is the conditioning drawing itself, so what flat shows and what
      // generators are shown never drift apart.
      const svg = req.condition.svg || sceneSvg(req.wireframe.regions, req.canvas, req.style);
      return { key: req.key, mime: "image/png", bytes: rasterize(svg), meta: { renderer: "flat" } };
    },
  };
}
