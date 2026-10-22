// Where a generated subject can go without sitting behind a fact: the largest
// empty rectangle in the safe area, clear of every content region and panel.
// Pure, like the rest of layout.

import type { Wireframe } from "./layout";
import type { Rect } from "./model";

export interface FreeAreaOptions {
  /** Cells per side of the occupancy grid. */
  grid?: number;
  /** Clearance kept around each region, as a fraction of the canvas. */
  pad?: number;
}

/** The largest empty rectangle (by canvas pixels) inside the safe area, or undefined if there is none. */
export function largestFreeArea(wf: Wireframe, opts: FreeAreaOptions = {}): Rect | undefined {
  const G = opts.grid ?? 48;
  const pad = opts.pad ?? 0.02;
  const [sx, sy, sw, sh] = wf.safe;
  const cw = sw / G;
  const ch = sh / G;

  // Mark every grid cell a padded region touches.
  const occupied = Array.from({ length: G }, () => new Uint8Array(G));
  for (const r of wf.regions) {
    if (r.z !== 2 && r.kind !== "panel") continue;
    const [x, y, w, h] = r.rect;
    const gx0 = Math.max(0, Math.floor((x - pad - sx) / cw));
    const gy0 = Math.max(0, Math.floor((y - pad - sy) / ch));
    const gx1 = Math.min(G, Math.ceil((x + w + pad - sx) / cw));
    const gy1 = Math.min(G, Math.ceil((y + h + pad - sy) / ch));
    for (let gy = gy0; gy < gy1; gy++) for (let gx = gx0; gx < gx1; gx++) occupied[gy]![gx] = 1;
  }

  // Largest all-free rectangle: a histogram of free run lengths per row, scanned with a stack.
  const cellArea = cw * wf.canvas.w * ch * wf.canvas.h;
  const heights = new Array<number>(G).fill(0);
  let best: { area: number; gx: number; gy: number; w: number; h: number } | undefined;
  for (let gy = 0; gy < G; gy++) {
    for (let gx = 0; gx < G; gx++) heights[gx] = occupied[gy]![gx] ? 0 : heights[gx]! + 1;
    const stack: number[] = [];
    for (let gx = 0; gx <= G; gx++) {
      const hgt = gx === G ? 0 : heights[gx]!;
      while (stack.length && heights[stack[stack.length - 1]!]! >= hgt) {
        const top = stack.pop()!;
        const height = heights[top]!;
        const left = stack.length ? stack[stack.length - 1]! + 1 : 0;
        const width = gx - left;
        const area = width * height * cellArea;
        if (height > 0 && (!best || area > best.area)) best = { area, gx: left, gy: gy - height + 1, w: width, h: height };
      }
      stack.push(gx);
    }
  }
  if (!best) return undefined;
  const round = (n: number) => Math.round(n * 1e4) / 1e4;
  return [round(sx + best.gx * cw), round(sy + best.gy * ch), round(best.w * cw), round(best.h * ch)];
}

/** Plain words for where a rectangle sits in the frame, for prompts. */
export function describeArea(rect: Rect): string {
  const [x, y, w, h] = rect;
  const cx = x + w / 2;
  const cy = y + h / 2;
  const row = cy < 0.4 ? "upper" : cy > 0.6 ? "lower" : "middle";
  if (w > 0.6) return row === "middle" ? "the middle band of the frame" : `the ${row} part of the frame, across its width`;
  if (h > 0.6) return `the ${cx < 0.5 ? "left" : "right"} side of the frame`;
  const col = cx < 0.4 ? "left" : cx > 0.6 ? "right" : "centre";
  return row === "middle" && col === "centre" ? "the centre of the frame" : `the ${row} ${col} of the frame`;
}
