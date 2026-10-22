// Region validation for generated scenes (spec §7.3): every `reserved` region
// must be calm (low luminance variance) and dark or light enough that the
// style's foreground colour reads on it at WCAG AA. Failing regions are
// re-rolled by the host; if they keep failing, a flat fill is composited into
// those regions only.

import sharp from "sharp";
import { type Region, type SceneAsset, type StylePack, type Wireframe, contrast, hexToRgb, mix } from "@videotape/core";
import type { RegionCheck, Validator } from "./host";

export type RegionStats = RegionCheck;

export interface ValidatorOptions {
  /** Highest luma spread a reserved region may have. */
  maxSpread?: number;
  /** Lowest contrast against the foreground colour (WCAG AA body text: 4.5). */
  minContrast?: number;
  /** Validation runs on a downscaled copy; this is the divisor. */
  scale?: number;
  /** Output format for stored generated scenes. */
  format?: "webp" | "png";
}

const reservedRegions = (wf: Wireframe): Region[] => wf.regions.filter((r) => r.z === 2 && r.mask === "reserved");

export async function regionStats(bytes: Uint8Array, wf: Wireframe, style: StylePack, opts: ValidatorOptions = {}): Promise<RegionStats[]> {
  const div = opts.scale ?? 4;
  const w = Math.max(1, Math.round(wf.canvas.w / div));
  const h = Math.max(1, Math.round(wf.canvas.h / div));
  const { data } = await sharp(bytes).resize(w, h, { fit: "fill" }).removeAlpha().raw().toBuffer({ resolveWithObject: true });
  const fg = hexToRgb(style.palette.fg);
  return reservedRegions(wf).map((r) => {
    const x0 = Math.max(0, Math.floor(r.rect[0] * w));
    const y0 = Math.max(0, Math.floor(r.rect[1] * h));
    const x1 = Math.min(w, Math.max(x0 + 1, Math.ceil((r.rect[0] + r.rect[2]) * w)));
    const y1 = Math.min(h, Math.max(y0 + 1, Math.ceil((r.rect[1] + r.rect[3]) * h)));
    let n = 0, sr = 0, sg = 0, sb = 0, sl = 0, sl2 = 0;
    for (let y = y0; y < y1; y++) {
      for (let x = x0; x < x1; x++) {
        const i = (y * w + x) * 3;
        const R = data[i]!, G = data[i + 1]!, B = data[i + 2]!;
        const l = 0.2126 * R + 0.7152 * G + 0.0722 * B;
        n++; sr += R; sg += G; sb += B; sl += l; sl2 += l * l;
      }
    }
    const mean = sl / n;
    const spread = Math.sqrt(Math.max(0, sl2 / n - mean * mean));
    const c = contrast([sr / n, sg / n, sb / n], fg);
    const ok = spread <= (opts.maxSpread ?? 24) && c >= (opts.minContrast ?? 4.5);
    return { id: r.id, spread: Math.round(spread * 10) / 10, contrast: Math.round(c * 100) / 100, ok };
  });
}

/** Paints a soft flat fill from the style palette over the given regions only. */
export async function patchRegions(bytes: Uint8Array, wf: Wireframe, style: StylePack, ids: string[], format: "webp" | "png" = "webp"): Promise<Uint8Array> {
  const { w, h } = wf.canvas;
  const fill = mix(style.palette.bg, style.palette.fg, 0.04);
  const pad = Math.min(w, h) * 0.01;
  const rects = wf.regions
    .filter((r) => ids.includes(r.id))
    .map((r) => {
      const x = r.rect[0] * w - pad, y = r.rect[1] * h - pad, rw = r.rect[2] * w + 2 * pad, rh = r.rect[3] * h + 2 * pad;
      return `<rect x="${x}" y="${y}" width="${rw}" height="${rh}" rx="${pad * 1.5}" fill="${fill}" fill-opacity="0.94"/>`;
    })
    .join("");
  const overlay = Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">${rects}</svg>`);
  const out = sharp(bytes).resize(w, h, { fit: "fill" }).composite([{ input: overlay }]);
  return new Uint8Array(await (format === "png" ? out.png() : out.webp({ quality: 88 })).toBuffer());
}

/** The sharp-backed validator the host uses for every non-deterministic renderer. */
export function sharpValidator(opts: ValidatorOptions = {}): Validator {
  const format = opts.format ?? "webp";
  const mime = format === "png" ? "image/png" : "image/webp";
  return {
    async normalize(asset: SceneAsset, wf: Wireframe): Promise<SceneAsset> {
      // Backends round sizes (to multiples of 8 or 16); the stage needs the canonical canvas exactly.
      const img = sharp(asset.bytes).resize(wf.canvas.w, wf.canvas.h, { fit: "cover" });
      const bytes = new Uint8Array(await (format === "png" ? img.png() : img.webp({ quality: 88 })).toBuffer());
      return { ...asset, mime, bytes };
    },
    async check(asset, wf, style) {
      const regions = await regionStats(asset.bytes, wf, style, opts);
      return { failing: regions.filter((s) => !s.ok).map((s) => s.id), regions };
    },
    async patch(asset, wf, style, failing) {
      return { ...asset, mime, bytes: await patchRegions(asset.bytes, wf, style, failing, format) };
    },
  };
}
