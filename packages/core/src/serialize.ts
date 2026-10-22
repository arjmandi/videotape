// Authoring objects → wire JSON (spec §5.4). Handler bodies and hook functions
// are dropped; only declared outcomes and "has a hook" flags survive.

import { type App, type Component, type Frame, type Tape, DEFAULT_STYLE, isBind, tapeEntry } from "./model";
import type { AppSpec, ComponentSpec, FrameSpec, TapeSpec } from "./schema";
import { BUILTIN_STYLES } from "./style";

/** JSON.stringify with sorted object keys, so equal values give equal strings. */
export function canonicalJson(value: unknown): string {
  return JSON.stringify(value, (_k, v) =>
    v && typeof v === "object" && !Array.isArray(v)
      ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)))
      : v,
  );
}

export function componentSpec(c: Component): ComponentSpec {
  // Components are already plain data apart from select options given as a Bind.
  const out = { ...c } as Record<string, unknown>;
  if (c.kind === "select" && isBind(c.options)) out.options = { bind: c.options.bind };
  return out as ComponentSpec;
}

export function frameSpec(f: Frame): FrameSpec {
  const out: FrameSpec = { id: f.id, components: f.components.map(componentSpec) };
  if (f.title !== undefined) out.title = f.title;
  if (f.layout !== undefined) out.layout = f.layout;
  if (typeof f.scene === "string") out.scene = f.scene;
  else if (typeof f.scene === "function") out.scene = { dynamic: true };
  if (f.flavour) out.flavour = true;
  if (f.enter) out.enter = true;
  if (f.cut !== undefined) out.cut = f.cut;
  if (f.on) {
    out.on = Object.fromEntries(
      Object.entries(f.on).map(([name, h]) => [name, h.outcomes ? { outcomes: h.outcomes } : {}]),
    );
  }
  return out;
}

export function tapeSpec(t: Tape): TapeSpec {
  const out: TapeSpec = {
    id: t.id,
    style: t.style ?? DEFAULT_STYLE,
    entry: tapeEntry(t) ?? "",
    frames: t.frames.map(frameSpec),
  };
  if (t.title !== undefined) out.title = t.title;
  return out;
}

export function toSpec(a: App): AppSpec {
  const own = a.styles ?? [];
  const builtins = BUILTIN_STYLES.filter((b) => !own.some((s) => s.id === b.id));
  return { v: 1, entry: a.entry, tapes: a.tapes.map(tapeSpec), styles: [...own, ...builtins] };
}
