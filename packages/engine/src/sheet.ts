// A contact sheet for reviewing generated scenes: each scene with its checked
// regions outlined (green passed, red failed, amber patched; surfaces dashed)
// and the numbers region validation used. For people, not for players.

import sharp from "sharp";
import type { Wireframe } from "@videotape/core";
import type { Cache } from "./cache";
import type { RegionCheck } from "./host";

export interface SheetTile {
  title: string;
  subtitle: string;
  file: string;
  wireframe: Wireframe;
  regions?: RegionCheck[];
  patched?: string[];
}

const TILE_H = 360;
const CAPTION_H = 54;
const GAP = 20;
const MAX_W = 1880;

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

function overlay(t: SheetTile, w: number, h: number): Buffer {
  const parts: string[] = [];
  for (const r of t.wireframe.regions) {
    if (!((r.z === 2 && r.mask === "reserved") || r.mask === "surface")) continue;
    const check = t.regions?.find((c) => c.id === r.id);
    const patched = t.patched?.includes(r.id);
    const color = patched ? "#fbbf24" : !check ? "#9ca3af" : check.ok ? "#4ade80" : "#f87171";
    const [x, y, rw, rh] = [r.rect[0] * w, r.rect[1] * h, r.rect[2] * w, r.rect[3] * h];
    const dash = r.mask === "surface" ? ` stroke-dasharray="5 3"` : "";
    parts.push(`<rect x="${x}" y="${y}" width="${rw}" height="${rh}" fill="none" stroke="${color}" stroke-width="1.5"${dash}/>`);
    // Passing surfaces stay unlabelled so the sheet stays readable.
    if (check && (r.mask === "reserved" || !check.ok)) {
      const nums = r.mask === "reserved" ? ` σ${check.spread} c${check.contrast}` : "";
      const label = `${r.id}${nums}${check.words ? ` “${check.text ?? ""}”` : ""}`;
      parts.push(`<text x="${x + 2}" y="${y + 10}" font-family="Menlo, monospace" font-size="9" fill="${color}" stroke="#000" stroke-width="2.5" paint-order="stroke">${esc(label)}</text>`);
    }
  }
  parts.push(`<text x="0" y="${h + 20}" font-family="Helvetica, Arial, sans-serif" font-size="15" font-weight="700" fill="#f3ede4">${esc(t.title)}</text>`);
  parts.push(`<text x="0" y="${h + 40}" font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#a8a2b2">${esc(t.subtitle)}</text>`);
  return Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h + CAPTION_H}">${parts.join("")}</svg>`);
}

/** Lays tiles out in rows at a common height and returns a PNG. */
export async function contactSheet(tiles: SheetTile[], cache: Cache): Promise<Uint8Array> {
  type Placed = { t: SheetTile; x: number; y: number; w: number };
  const placed: Placed[] = [];
  let x = GAP, y = GAP, width = 0;
  for (const t of tiles) {
    const w = Math.round((TILE_H * t.wireframe.canvas.w) / t.wireframe.canvas.h);
    if (x + w + GAP > MAX_W && x > GAP) {
      x = GAP;
      y += TILE_H + CAPTION_H + GAP;
    }
    placed.push({ t, x, y, w });
    x += w + GAP;
    width = Math.max(width, x);
  }
  const height = y + TILE_H + CAPTION_H + GAP;
  const layers: sharp.OverlayOptions[] = [];
  for (const p of placed) {
    const asset = await cache.getAsset(p.t.file);
    if (!asset) continue;
    const img = await sharp(asset.bytes).resize(p.w, TILE_H, { fit: "fill" }).png().toBuffer();
    layers.push({ input: img, left: p.x, top: p.y });
    layers.push({ input: overlay(p.t, p.w, TILE_H), left: p.x, top: p.y });
  }
  const sheet = sharp({ create: { width: Math.max(width, 200), height, channels: 3, background: "#0e0d12" } }).composite(layers);
  return new Uint8Array(await sheet.png().toBuffer());
}
