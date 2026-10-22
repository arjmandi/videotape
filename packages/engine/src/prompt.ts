// Prompt composition (spec §5.5): style.prefix + scene + layout hints + style.suffix.
// Layout hints come from the wireframe, so the generator keeps calm space where
// the facts go. Reel data never reaches this function; only flavour does.

import type { Flavour, Frame, Region, StylePack, Wireframe } from "@videotape/core";

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

export function composePrompt(style: StylePack, scene: string, wf: Wireframe): string {
  const hints = layoutHints(wf);
  return `${style.prompt.prefix}${scene}${hints ? `, ${hints}` : ""}${style.prompt.suffix}`;
}
