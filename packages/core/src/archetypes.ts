// Archetypes, their slots, and slot assignment (spec §6.2).

import { type Archetype, type ComponentKind, VALUE_KINDS } from "./model";

export interface SlotDef {
  name: string;
  /** Numbered slots (`form.field.N`, `grid.cell.N`) expand to `name.1`, `name.2`, … */
  repeat?: boolean;
  /** Kinds auto-placement may put here. Explicit `slot:` accepts any kind. */
  auto: readonly ComponentKind[];
}

const VALUE = VALUE_KINDS;
const NAV_LEADING: SlotDef = { name: "nav.leading", auto: ["link"] };
const NAV_TRAILING: SlotDef = { name: "nav.trailing", auto: ["link", "button"] };

/** Slots in tab order. */
export const ARCHETYPE_SLOTS: Record<Archetype, readonly SlotDef[]> = {
  hero: [
    NAV_LEADING, NAV_TRAILING,
    { name: "hero.title", auto: ["text"] },
    { name: "hero.subtitle", auto: ["text"] },
    { name: "hero.primary", auto: ["button", "link"] },
    { name: "hero.secondary", auto: ["button", "link"] },
    { name: "hero.media", auto: ["image", "media"] },
    { name: "footer", auto: ["text"] },
  ],
  form: [
    NAV_LEADING,
    { name: "form.title", auto: ["text"] },
    { name: "form.field", repeat: true, auto: VALUE },
    { name: "form.error", auto: ["text"] },
    { name: "form.primary", auto: ["button"] },
    { name: "form.secondary", auto: ["link", "button"] },
    { name: "form.aside", auto: ["text", "image", "media"] },
  ],
  list: [
    NAV_LEADING, NAV_TRAILING,
    { name: "list.title", auto: ["text"] },
    { name: "list.search", auto: ["input"] },
    { name: "list.items", auto: ["list"] },
    { name: "list.primary", auto: ["button"] },
  ],
  detail: [
    NAV_LEADING, NAV_TRAILING,
    { name: "detail.title", auto: ["text"] },
    { name: "detail.media", auto: ["image", "media"] },
    { name: "detail.body", auto: ["text"] },
    { name: "detail.meta", auto: ["text"] },
    { name: "detail.primary", auto: ["button"] },
    { name: "detail.secondary", auto: ["button", "link"] },
  ],
  grid: [
    NAV_LEADING, NAV_TRAILING,
    { name: "grid.title", auto: ["text"] },
    { name: "grid.cell", repeat: true, auto: ["text", "button", "image", "media", "list", ...VALUE] },
    { name: "grid.aside", auto: ["text", "list", "image"] },
  ],
  reader: [
    NAV_LEADING,
    { name: "reader.title", auto: ["text"] },
    { name: "reader.body", auto: ["text"] },
    { name: "reader.toc", auto: ["list"] },
  ],
  blank: [],
};

/** Upper bound on numbered slots, so a typo cannot ask for cell 9999. */
export const MAX_REPEAT = 16;

export interface ParsedSlot {
  def: SlotDef;
  /** Position in tab order. */
  order: number;
  index?: number;
}

export function parseSlot(archetype: Archetype, slot: string): ParsedSlot | undefined {
  const defs = ARCHETYPE_SLOTS[archetype];
  for (const [i, def] of defs.entries()) {
    if (!def.repeat && slot === def.name) return { def, order: i * 100 };
    if (def.repeat && slot.startsWith(def.name + ".")) {
      const n = Number(slot.slice(def.name.length + 1));
      if (Number.isInteger(n) && n >= 1 && n <= MAX_REPEAT) return { def, order: i * 100 + n, index: n };
    }
  }
  return undefined;
}

export interface Placeable {
  id: string;
  kind: ComponentKind;
  slot?: string;
  variant?: string;
}

export interface SlotIssue {
  code: "unknown-slot" | "slot-taken" | "no-slot-available";
  component: string;
  slot?: string;
}

export interface SlotAssignment {
  /** Component id → slot name, in tab order. */
  slots: Map<string, string>;
  issues: SlotIssue[];
}

/** Explicit slots first, then auto-placement in declaration order (spec §6.2). */
export function assignSlots(archetype: Archetype, components: readonly Placeable[]): SlotAssignment {
  const issues: SlotIssue[] = [];
  const taken = new Map<string, string>(); // slot → component id
  const bySlot = new Map<string, string>(); // component id → slot

  if (archetype === "blank") return { slots: bySlot, issues };

  for (const c of components) {
    if (c.slot === undefined) continue;
    if (!parseSlot(archetype, c.slot)) {
      issues.push({ code: "unknown-slot", component: c.id, slot: c.slot });
      continue;
    }
    if (taken.has(c.slot)) {
      issues.push({ code: "slot-taken", component: c.id, slot: c.slot });
      continue;
    }
    taken.set(c.slot, c.id);
    bySlot.set(c.id, c.slot);
  }

  for (const c of components) {
    if (c.slot !== undefined) continue;
    const slot = firstFreeSlot(archetype, c.kind, taken);
    if (!slot) {
      issues.push({ code: "no-slot-available", component: c.id });
      continue;
    }
    taken.set(slot, c.id);
    bySlot.set(c.id, slot);
  }

  const ordered = [...bySlot.entries()].sort(
    ([, a], [, b]) => (parseSlot(archetype, a)?.order ?? 0) - (parseSlot(archetype, b)?.order ?? 0),
  );
  return { slots: new Map(ordered), issues };
}

function firstFreeSlot(archetype: Archetype, kind: ComponentKind, taken: Map<string, string>): string | undefined {
  for (const def of ARCHETYPE_SLOTS[archetype]) {
    if (!def.auto.includes(kind)) continue;
    if (!def.repeat) {
      if (!taken.has(def.name)) return def.name;
      continue;
    }
    for (let n = 1; n <= MAX_REPEAT; n++) {
      const name = `${def.name}.${n}`;
      if (!taken.has(name)) return name;
    }
  }
  return undefined;
}

/** Spec §6.2: inputs → form; a list → list; many number texts → grid; otherwise hero. */
export function inferArchetype(components: readonly Placeable[]): Archetype {
  if (components.some((c) => VALUE_KINDS.includes(c.kind))) return "form";
  if (components.some((c) => c.kind === "list")) return "list";
  if (components.filter((c) => c.kind === "text" && c.variant === "number").length >= 3) return "grid";
  return "hero";
}
