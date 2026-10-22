// Cache keys (spec §7.2). Reel data is never part of a key: facts live on the
// content layer, so one scene asset serves every user.

import { createHash } from "node:crypto";
import { CORE_VERSION, type Flavour, type Frame, canonicalJson, resolveArchetype } from "@videotape/core";

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
  style: { id: string };
  seed: number;
  flavour: Flavour;
}

export function sceneKey(p: KeyParts): string {
  return "sha256:" + sha256(
    CORE_VERSION, p.renderer.id, p.renderer.version, p.frameHash, p.viewportClass, p.style.id, String(p.seed), canonicalJson(p.flavour),
  );
}
