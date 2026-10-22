// Region validation for generated scenes (spec §7.3): every `reserved` region
// must be calm (low luminance variance) and dark or light enough that the
// style's foreground colour reads on it at WCAG AA. Every region, `surface`
// ones (button faces, panels) included, must be free of lettering: image
// models paint fake text and controls, and thin strokes barely move variance,
// so lettering is found by OCR (see ./lettering). Failing regions are re-rolled
// by the host; if they keep failing, a flat fill is composited into those
// regions only.

import sharp from "sharp";
import { type Region, type SceneAsset, type StylePack, type Wireframe, contrast, hexToRgb, mix } from "@videotape/core";
import type { RegionCheck, Validator } from "./host";
import { type LetteringOptions, findLettering, overlap } from "./lettering";

export type RegionStats = RegionCheck;

export interface ValidatorOptions {
  /** Highest luma spread a reserved region may have, over the whole region. */
  maxSpread?: number;
  /**
   * Highest luma spread in any tile of a reserved region. Averaged over a long subtitle, a small
   * object behind two words barely moves the spread; per tile, it stands out.
   */
  maxTileSpread?: number;
  /** Tile side in pixels of the downscaled copy (16 at 1/4 scale is 64 canvas px, about a word). */
  tile?: number;
  /** Lowest contrast against the foreground colour (WCAG AA body text: 4.5). */
  minContrast?: number;
  /** Spread and contrast run on a copy downscaled by this divisor. */
  scale?: number;
  /** Lettering detection; `false` turns it off. */
  lettering?: LetteringOptions | false;
  /** Output format for stored generated scenes. */
  format?: "webp" | "png";
}

export const DEFAULTS = { maxSpread: 24, maxTileSpread: 30, tile: 16, minContrast: 4.5, scale: 4 } as const;

/**
 * Bumped whenever a check changes, so cached scenes made under older checks are checked again.
 * 1: spread and contrast. 2: lettering. 3: spread per tile.
 */
export const VALIDATOR_VERSION = "3";

/** Luma spread over a box of an RGB buffer w pixels wide. */
function spreadOf(data: Uint8Array | Buffer, w: number, x0: number, y0: number, x1: number, y1: number): number {
  let n = 0, s = 0, s2 = 0;
  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) {
      const i = (y * w + x) * 3;
      const l = 0.2126 * data[i]! + 0.7152 * data[i + 1]! + 0.0722 * data[i + 2]!;
      n++; s += l; s2 += l * l;
    }
  }
  const m = s / n;
  return Math.sqrt(Math.max(0, s2 / n - m * m));
}

/** Worst spread over half-overlapping square tiles covering the box. */
function worstTile(data: Uint8Array | Buffer, w: number, box: [number, number, number, number], side: number): number {
  const [x0, y0, x1, y1] = box;
  const s = Math.max(4, Math.min(side, x1 - x0, y1 - y0));
  const step = Math.max(1, Math.floor(s / 2));
  let worst = 0;
  for (let ty = y0; ty < y1; ty += step) {
    for (let tx = x0; tx < x1; tx += step) {
      worst = Math.max(worst, spreadOf(data, w, tx, ty, Math.min(x1, tx + s), Math.min(y1, ty + s)));
      if (tx + s >= x1) break;
    }
    if (ty + s >= y1) break;
  }
  return worst;
}

/** Regions validation looks at: reserved content, and surfaces (button faces and panels). */
const checkedRegions = (wf: Wireframe): Region[] => wf.regions.filter((r) => (r.z === 2 && r.mask === "reserved") || r.mask === "surface");

/** Pixel bounds of a region on a w×h grid. */
function bounds(r: Region, w: number, h: number): [number, number, number, number] {
  const [rx, ry, rw, rh] = r.rect;
  const x0 = Math.max(0, Math.floor(rx * w));
  const y0 = Math.max(0, Math.floor(ry * h));
  const x1 = Math.min(w, Math.max(x0 + 1, Math.ceil((rx + rw) * w)));
  const y1 = Math.min(h, Math.max(y0 + 1, Math.ceil((ry + rh) * h)));
  return [x0, y0, x1, y1];
}

export async function regionStats(bytes: Uint8Array, wf: Wireframe, style: StylePack, opts: ValidatorOptions = {}): Promise<RegionStats[]> {
  const o = { ...DEFAULTS, ...opts };
  const w = Math.max(1, Math.round(wf.canvas.w / o.scale));
  const h = Math.max(1, Math.round(wf.canvas.h / o.scale));
  const { data } = await sharp(bytes).resize(w, h, { fit: "fill" }).removeAlpha().raw().toBuffer({ resolveWithObject: true });
  const words = opts.lettering === false ? [] : await findLettering(bytes, wf.canvas, opts.lettering ?? {});
  const fg = hexToRgb(style.palette.fg);
  return checkedRegions(wf).map((r): RegionStats => {
    // A word belongs to the region that holds most of it.
    const inside = words.filter((x) => overlap(x.rect, r.rect) >= 0.5);
    const lettering = inside.length ? { words: inside.length, text: inside.map((x) => x.text).join(" ").slice(0, 80) } : { words: 0 };
    if (r.mask === "surface") {
      const ok = inside.length === 0;
      return { id: r.id, mask: "surface", ...lettering, ok, ...(ok ? {} : { why: ["lettering"] }) };
    }
    const [x0, y0, x1, y1] = bounds(r, w, h);
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
    const tileSpread = worstTile(data, w, [x0, y0, x1, y1], o.tile);
    const c = contrast([sr / n, sg / n, sb / n], fg);
    const why = [
      ...(spread > o.maxSpread || tileSpread > o.maxTileSpread ? ["busy"] : []),
      ...(c < o.minContrast ? ["contrast"] : []),
      ...(inside.length ? ["lettering"] : []),
    ];
    return {
      id: r.id, mask: "reserved", spread: Math.round(spread * 10) / 10, tileSpread: Math.round(tileSpread * 10) / 10,
      contrast: Math.round(c * 100) / 100,
      ...lettering, ok: why.length === 0, ...(why.length ? { why } : {}),
    };
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
    version: VALIDATOR_VERSION,
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
