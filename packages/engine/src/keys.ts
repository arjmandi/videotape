// Cache keys (spec §7.2). Reel data is never part of a key: facts live on the
// content layer, so one scene asset serves every user.

import { createHash } from "node:crypto";
import { CORE_VERSION, type Flavour, type Frame, type StylePack, canonicalJson, resolveArchetype } from "@videotape/core";

export function sha256(...parts: string[]): string {
  const h = createHash("sha256");
  for (const p of parts) h.update(p).update("\0");
  return h.digest("hex");
}

/** Scene text, layout, and components (ids, kinds, slots, static labels). */
export function frameSpecHash(frame: Frame): string {
  return sha256(canonicalJson({
    scene: typeof frame.scene === "function" ? "ƒ" : frame.scene ?? "",
    layout: resolveArchetype(frame),
    components: frame.components.map((c) => ({
      id: c.id,
      kind: c.kind,
      slot: c.slot ?? null,
      rect: c.rect ?? null,
      label: "label" in c ? c.label ?? null : null,
      value: c.kind === "text" ? c.value ?? null : null,
      emphasis: c.kind === "button" ? c.emphasis ?? null : null,
    })),
  }));
}

export interface KeyParts {
  renderer: { id: string; version: string };
  frameHash: string;
  viewportClass: string;
  /** The whole style pack, so editing a prefix or a colour starts a fresh cache. */
  style: StylePack;
  seed: number;
  flavour: Flavour;
  /** What the renderer is shown: the conditioning drawing. */
  condition: string;
  /** The composed prompt; empty for deterministic renderers, which ignore it. */
  prompt: string;
}

/**
 * Spec §7.2, extended: besides the listed parts, the key covers everything a
 * renderer is given (style pack, drawing, prompt), so no input can change
 * without the key changing. Reel data is still never part of it.
 */
export function sceneKey(p: KeyParts): string {
  return "sha256:" + sha256(
    CORE_VERSION, p.renderer.id, p.renderer.version, p.frameHash, p.viewportClass, p.style.id, String(p.seed), canonicalJson(p.flavour),
    sha256(canonicalJson(p.style)), sha256(p.condition), p.prompt,
  );
}
