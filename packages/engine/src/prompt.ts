// Prompt composition (spec §5.5): style.prefix + scene + layout hints + style.suffix.
// Layout hints come from the wireframe, so the generator keeps calm space where
// the facts go. Reel data never reaches this function; only flavour does.

import { type Flavour, type Frame, type Rect, type Region, type StylePack, type Wireframe, describeArea } from "@videotape/core";

function where(r: Region): string {
  const [x, y, w, h] = r.rect;
  const cx = x + w / 2;
  const cy = y + h / 2;
  const col = cx < 0.36 ? "left" : cx > 0.64 ? "right" : "centre";
  const row = cy < 0.36 ? "upper" : cy > 0.64 ? "lower" : "middle";
  const big = w > 0.6 && h > 0.6;
  return big ? "most of the frame" : row === "middle" && col === "centre" ? "the centre" : `the ${row} ${col}`;
}

export function layoutHints(wf: Wireframe): string {
  const hints = new Set<string>();
  for (const r of wf.regions) {
    if (r.kind === "panel") hints.add(`a calm, softly lit panel in ${where(r)}`);
  }
  const loose = wf.regions.filter((r) => r.z === 2 && r.mask === "reserved");
  for (const r of loose) hints.add(`calm, untextured negative space in ${where(r)}`);
  return [...hints].join(", ");
}

export function sceneText(frame: Frame, flavour: Flavour): string {
  if (typeof frame.scene === "function") return frame.scene(flavour);
  return frame.scene ?? "An abstract, calm backdrop";
}

/** Bounding box of rectangles, as a rect. */
function bounds(rects: Rect[]): Rect {
  const x0 = Math.min(...rects.map((r) => r[0]));
  const y0 = Math.min(...rects.map((r) => r[1]));
  const x1 = Math.max(...rects.map((r) => r[0] + r[2]));
  const y1 = Math.max(...rects.map((r) => r[1] + r[3]));
  return [x0, y0, x1 - x0, y1 - y0];
}

/**
 * Tells the generator where the subject goes, and where nothing should go: the area the
 * headline and controls occupy (the nav row and footer are left out; they hug the edges).
 */
export function subjectHint(focus: Rect, wf: Wireframe): string {
  const main = wf.regions.filter((r) => r.z === 2 && !r.slot?.startsWith("nav.") && r.slot !== "footer");
  const keepClear = main.length ? `, nothing in ${describeArea(bounds(main.map((r) => r.rect)))}` : "";
  return `the main subject placed in ${describeArea(focus)}${keepClear}`;
}

export function composePrompt(style: StylePack, scene: string, wf: Wireframe, focus?: Rect): string {
  const hints = layoutHints(wf);
  const subject = focus ? `, ${subjectHint(focus, wf)}` : "";
  return `${style.prompt.prefix}${scene}${subject}${hints ? `, ${hints}` : ""}${style.prompt.suffix}`;
}
