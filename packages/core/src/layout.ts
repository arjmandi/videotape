// The layout engine (spec §6): layout(frame, viewportClass, style) → Wireframe.
// Pure and deterministic. Every region is decided here, before any pixel is
// generated; the same wireframe conditions the generator and places the facts.

import { assignSlots, inferArchetype, type Placeable, type SlotIssue } from "./archetypes";
import type { Archetype, ComponentKind, Rect } from "./model";
import type { StylePack } from "./style";
import { wireframeSvg } from "./svg";
import { CANVAS, SAFE_MARGIN, type Size, type ViewportClass } from "./viewport";

export type Mask = "reserved" | "surface" | "free";
export type TypeRole = "display" | "title" | "subtitle" | "body" | "caption" | "number" | "control";

/** Typography decided by layout so the content layer and the wireframe agree. Sizes in canvas px. */
export interface TypeHint {
  role: TypeRole;
  size: number;
  lines: number;
  align: "start" | "center" | "end";
}

export interface Region {
  id: string;
  kind: ComponentKind | "panel";
  rect: Rect;
  mask: Mask;
  z: 1 | 2;
  slot?: string;
  type?: TypeHint;
  /** Input-like regions reserve their top part for a visible label. Canvas px. */
  labelSize?: number;
  emphasis?: "primary" | "secondary";
}

/** A button's emphasis: declared, or primary when it sits in a `*.primary` slot. */
export function emphasisOf(c: { kind: string; emphasis?: string }, slot: string | undefined): "primary" | "secondary" | undefined {
  if (c.kind !== "button") return undefined;
  if (c.emphasis === "primary" || c.emphasis === "secondary") return c.emphasis;
  return slot?.endsWith(".primary") ? "primary" : "secondary";
}

export interface LayoutDiagnostic {
  code: SlotIssue["code"] | "missing-rect" | "overflow";
  component?: string;
  slot?: string;
  message: string;
}

export interface Wireframe {
  canvas: Size;
  viewportClass: ViewportClass;
  archetype: Archetype;
  safe: Rect;
  regions: Region[];
  svg: string;
  diagnostics: LayoutDiagnostic[];
}

/** The parts of a frame the layout engine reads. Both authoring frames and wire specs fit. */
export interface LayoutFrame {
  id: string;
  layout?: Archetype;
  components: ReadonlyArray<Placeable & { rect?: Rect; emphasis?: string; type?: string }>;
}

/** Canvas px per density-independent unit, chosen so 1 unit ≈ 1 CSS px on a typical device. */
export const DENSITY: Record<ViewportClass, number> = { desktop: 1.33, tablet: 2, phone: 2.75 };

/** Type scale in units per class. */
export const TYPE_SCALE: Record<ViewportClass, Record<TypeRole, number>> = {
  desktop: { display: 64, title: 40, subtitle: 22, body: 17, caption: 14, number: 40, control: 17 },
  tablet: { display: 52, title: 36, subtitle: 20, body: 17, caption: 14, number: 36, control: 17 },
  phone: { display: 34, title: 28, subtitle: 18, body: 16, caption: 14, number: 30, control: 17 },
};

export const LINE_HEIGHT: Record<TypeRole, number> = {
  display: 1.12, title: 1.15, subtitle: 1.3, body: 1.45, caption: 1.35, number: 1.15, control: 1.3,
};

const MASK: Record<ComponentKind, Mask> = {
  text: "reserved", image: "reserved", media: "reserved", button: "surface", link: "reserved",
  input: "reserved", textarea: "reserved", select: "reserved", toggle: "reserved", slider: "reserved",
  date: "reserved", list: "reserved",
};

interface Box { x: number; y: number; w: number; h: number }
type Comp = LayoutFrame["components"][number];

/** Mutable state while laying out one frame. */
class Plan {
  readonly W: number;
  readonly H: number;
  readonly safe: Box;
  readonly bySlot = new Map<string, Comp>();
  readonly regions: Region[] = [];
  readonly diagnostics: LayoutDiagnostic[] = [];

  constructor(readonly cls: ViewportClass, readonly frame: LayoutFrame, slots: Map<string, string>) {
    ({ w: this.W, h: this.H } = CANVAS[cls]);
    this.safe = { x: this.W * SAFE_MARGIN, y: this.H * SAFE_MARGIN, w: this.W * (1 - 2 * SAFE_MARGIN), h: this.H * (1 - 2 * SAFE_MARGIN) };
    const byId = new Map(frame.components.map((c) => [c.id, c]));
    for (const [id, slot] of slots) this.bySlot.set(slot, byId.get(id)!);
  }

  u(n: number): number {
    return n * DENSITY[this.cls];
  }

  size(role: TypeRole): number {
    return this.u(TYPE_SCALE[this.cls][role]);
  }

  /** Height of `lines` lines of text in `role`. */
  textH(role: TypeRole, lines = 1): number {
    return this.size(role) * LINE_HEIGHT[role] * lines;
  }

  has(slot: string): boolean {
    return this.bySlot.has(slot);
  }

  get(slot: string): Comp | undefined {
    return this.bySlot.get(slot);
  }

  /** Occupied numbered slots under `name`, as [index, slot] sorted by index. */
  repeated(name: string): Array<[number, string]> {
    return [...this.bySlot.keys()]
      .filter((s) => s.startsWith(name + "."))
      .map((s) => [Number(s.slice(name.length + 1)), s] as [number, string])
      .sort((a, b) => a[0] - b[0]);
  }

  bottom(): number {
    return this.safe.y + this.safe.h;
  }

  /** Lays out the nav row if used and returns the y where content starts. */
  nav(): number {
    if (!this.has("nav.leading") && !this.has("nav.trailing")) return this.safe.y;
    const h = this.u(48);
    const { x, y, w } = this.safe;
    this.put("nav.leading", { x, y, w: Math.min(w * 0.45, this.u(320)), h });
    const tw = Math.min(w * 0.45, this.u(200));
    this.put("nav.trailing", { x: x + w - tw, y, w: tw, h }, "end");
    return y + h + this.u(28);
  }

  /** The text role a component in `slot` uses. */
  role(c: Comp, slot: string): TypeRole {
    if (c.kind !== "text") return c.kind === "list" ? "body" : "control";
    const v = c.variant as TypeRole | undefined;
    if (slot === "hero.title") return "display";
    if (v) return v;
    if (slot.endsWith(".title")) return "title";
    if (slot.endsWith(".subtitle") || slot.startsWith("nav.")) return "subtitle";
    if (slot === "form.error" || slot === "detail.meta" || slot === "footer") return "caption";
    return "body";
  }

  put(slot: string, box: Box, align: TypeHint["align"] = "start"): void {
    const c = this.bySlot.get(slot);
    if (!c) return;
    this.region(c, box, align, slot);
  }

  region(c: Comp, box: Box, align: TypeHint["align"], slot?: string): void {
    const role = this.role(c, slot ?? "");
    const size = this.size(role);
    const labelled = isLabelled(c);
    const textBox = labelled ? box.h - this.labelBlock() : box.h;
    const lines = role === "control" ? 1 : Math.max(1, Math.floor((textBox + 0.5) / (size * LINE_HEIGHT[role])));
    const r: Region = {
      id: c.id,
      kind: c.kind,
      rect: this.frac(box),
      mask: MASK[c.kind],
      z: 2,
      type: { role, size: round(size, 1), lines, align },
    };
    if (slot) r.slot = slot;
    if (labelled) r.labelSize = round(this.size("caption"), 1);
    const emphasis = emphasisOf(c, slot);
    if (emphasis) r.emphasis = emphasis;
    this.regions.push(r);
  }

  panel(id: string, box: Box): void {
    this.regions.push({ id, kind: "panel", rect: this.frac(box), mask: "surface", z: 1 });
  }

  /** Height of a labelled control: label line, gap, control. */
  fieldH(c: Comp | undefined): number {
    return c && isLabelled(c) ? this.labelBlock() + this.u(52) : this.u(52);
  }

  labelBlock(): number {
    return this.textH("caption") + this.u(6);
  }

  frac(b: Box): Rect {
    return [round(b.x / this.W), round(b.y / this.H), round(b.w / this.W), round(b.h / this.H)];
  }
}

function isLabelled(c: Comp): boolean {
  return ["input", "textarea", "select", "slider", "date"].includes(c.kind) && c.type !== "search";
}

function round(n: number, digits = 4): number {
  const f = 10 ** digits;
  return Math.round(n * f) / f;
}

// ── archetypes ──────────────────────────────────────────────────────────────

function hero(p: Plan): void {
  const { cls, safe } = p;
  const top = p.nav();
  const footerH = p.has("footer") ? p.textH("caption") + p.u(8) : 0;
  const bottom = p.bottom() - (footerH ? footerH + p.u(16) : 0);
  const media = p.has("hero.media");
  const wide = cls === "desktop";
  const col = wide
    ? media ? { x: safe.x, w: safe.w * 0.46 } : { x: safe.x + safe.w * 0.12, w: safe.w * 0.76 }
    : { x: safe.x, w: safe.w };
  const align = wide && !media ? "center" : "start";

  const titleH = p.has("hero.title") ? p.textH("display", cls === "phone" ? 2 : 1) : 0;
  const subH = p.has("hero.subtitle") ? p.textH("subtitle", cls === "phone" ? 3 : 2) : 0;
  const actions = ["hero.primary", "hero.secondary"].filter((s) => p.has(s));
  const btnH = p.u(52);
  const stacked = cls === "phone";
  const actionsH = actions.length === 0 ? 0 : stacked ? actions.length * btnH + (actions.length - 1) * p.u(12) : btnH;
  const gaps = [p.u(16), p.u(36), p.u(32)];
  const stackH = (parts: number[]) => {
    let total = 0;
    let n = 0;
    for (const [i, h] of parts.entries()) {
      if (!h) continue;
      if (n++) total += gaps[i - 1] ?? 0;
      total += h;
    }
    return total;
  };
  const room = bottom - top - stackH([titleH, subH, actionsH]) - gaps[2]!;
  const inlineMediaH = media && !wide ? Math.max(0, Math.min(col.w * 9 / 16, room)) : 0;
  const total = stackH([titleH, subH, actionsH, inlineMediaH]);
  let seen = 0;
  let y = top + Math.max(0, (bottom - top - total) / 2);
  const advance = (i: number, h: number) => {
    if (seen++) y += gaps[i - 1] ?? 0;
    const at = y;
    y += h;
    return at;
  };

  if (titleH) p.put("hero.title", { x: col.x, y: advance(0, titleH), w: col.w, h: titleH }, align);
  if (subH) p.put("hero.subtitle", { x: col.x, y: advance(1, subH), w: col.w, h: subH }, align);
  if (actionsH) {
    const ay = advance(2, actionsH);
    if (stacked) {
      actions.forEach((s, i) => p.put(s, { x: col.x, y: ay + i * (btnH + p.u(12)), w: col.w, h: btnH }));
    } else {
      const bw = p.u(220);
      const gap = p.u(16);
      const rowW = actions.length * bw + (actions.length - 1) * gap;
      const x0 = align === "center" ? col.x + (col.w - rowW) / 2 : col.x;
      actions.forEach((s, i) => p.put(s, { x: x0 + i * (bw + gap), y: ay, w: bw, h: btnH }));
    }
  }
  if (inlineMediaH) p.put("hero.media", { x: col.x, y: advance(3, inlineMediaH), w: col.w, h: inlineMediaH });
  if (media && wide) {
    const w = safe.w * 0.48;
    const h = Math.min(w * 9 / 16, bottom - top);
    p.put("hero.media", { x: safe.x + safe.w - w, y: top + (bottom - top - h) / 2, w, h });
  }
  if (footerH) p.put("footer", { x: safe.x, y: p.bottom() - footerH, w: safe.w, h: footerH }, align);
}

function form(p: Plan): void {
  const { cls, safe } = p;
  const top = p.nav();
  const pad = p.u(cls === "phone" ? 20 : 32);
  const fields = p.repeated("form.field");
  // Many fields go two to a row on wider screens; a phone keeps one column.
  const cols = cls !== "phone" && fields.length > 3 ? 2 : 1;
  const colGap = p.u(24);
  const colW = cls === "desktop" ? p.u(400) : cls === "tablet" ? Math.min(p.u(480), safe.w * 0.8) - 2 * pad : safe.w - 2 * pad;
  const innerW = Math.min(colW * cols + colGap * (cols - 1), safe.w - 2 * pad);
  const panelW = innerW + 2 * pad;

  type Item = { slots: string[]; h: number; gap: number };
  const items: Item[] = [];
  if (p.has("form.title")) items.push({ slots: ["form.title"], h: p.textH("title"), gap: p.u(24) });
  for (let i = 0; i < fields.length; i += cols) {
    const row = fields.slice(i, i + cols).map(([, slot]) => slot);
    items.push({ slots: row, h: Math.max(...row.map((s) => p.fieldH(p.get(s)))), gap: p.u(16) });
  }
  if (p.has("form.error")) items.push({ slots: ["form.error"], h: p.textH("caption", 2), gap: p.u(12) });
  if (p.has("form.primary")) items.push({ slots: ["form.primary"], h: p.u(52), gap: p.u(20) });
  if (p.has("form.secondary")) items.push({ slots: ["form.secondary"], h: p.u(48), gap: p.u(12) });
  const innerH = items.reduce((sum, it, i) => sum + it.h + (i ? it.gap : 0), 0);
  const panelH = innerH + 2 * pad;

  const aside = p.has("form.aside");
  const asideSide = aside && cls === "desktop";
  const asideW = p.u(300);
  const asideC = p.get("form.aside");
  const asideH = asideC?.kind === "text" ? p.textH(p.role(asideC, "form.aside"), 3) : p.u(140);
  const groupW = asideSide ? panelW + p.u(32) + asideW : panelW;
  const groupH = aside && !asideSide ? panelH + p.u(24) + asideH : panelH;
  const avail = p.bottom() - top;
  const px = safe.x + (safe.w - groupW) / 2;
  const py = top + Math.max(0, (avail - groupH) / 2);

  p.panel("__panel", { x: px, y: py, w: panelW, h: panelH });
  let y = py + pad;
  items.forEach((it, i) => {
    if (i) y += it.gap;
    const w = (innerW - colGap * (it.slots.length - 1)) / it.slots.length;
    it.slots.forEach((s, j) => p.put(s, { x: px + pad + j * (w + colGap), y, w, h: it.h }));
    y += it.h;
  });
  if (asideSide) p.put("form.aside", { x: px + panelW + p.u(32), y: py + pad, w: asideW, h: Math.min(asideH, panelH - 2 * pad) });
  else if (aside) p.put("form.aside", { x: px, y: py + panelH + p.u(24), w: panelW, h: asideH });
}

function list(p: Plan): void {
  const { cls, safe } = p;
  const top = p.nav();
  const col = cls === "desktop" ? { x: safe.x + safe.w * 0.18, w: safe.w * 0.64 } : { x: safe.x, w: safe.w };
  const primary = p.has("list.primary");
  const primaryInRow = primary && cls !== "phone";
  const btnH = p.u(52);
  let y = top;

  if (p.has("list.title") || primaryInRow) {
    const rowH = Math.max(p.has("list.title") ? p.textH("title") : 0, primaryInRow ? btnH : 0);
    const bw = p.u(200);
    const titleW = primaryInRow ? col.w - bw - p.u(16) : col.w;
    p.put("list.title", { x: col.x, y, w: titleW, h: rowH });
    if (primaryInRow) p.put("list.primary", { x: col.x + col.w - bw, y: y + (rowH - btnH) / 2, w: bw, h: btnH });
    y += rowH + p.u(20);
  }
  if (p.has("list.search")) {
    const h = p.fieldH(p.get("list.search"));
    p.put("list.search", { x: col.x, y, w: col.w, h });
    y += h + p.u(16);
  }
  let bottom = p.bottom();
  if (primary && !primaryInRow) {
    p.put("list.primary", { x: col.x, y: bottom - btnH, w: col.w, h: btnH });
    bottom -= btnH + p.u(16);
  }
  if (p.has("list.items")) {
    const inset = p.u(12);
    p.panel("__panel", { x: col.x, y, w: col.w, h: bottom - y });
    p.put("list.items", { x: col.x + inset, y: y + inset, w: col.w - 2 * inset, h: bottom - y - 2 * inset });
  }
}

function detail(p: Plan): void {
  const { cls, safe } = p;
  let y = p.nav();
  const bottom = p.bottom();
  if (p.has("detail.title")) {
    const h = p.textH("title", cls === "phone" ? 2 : 1);
    p.put("detail.title", { x: safe.x, y, w: safe.w, h });
    y += h + p.u(24);
  }
  const media = p.has("detail.media");
  const metaH = p.has("detail.meta") ? p.textH("caption", 2) : 0;
  const actions = ["detail.primary", "detail.secondary"].filter((s) => p.has(s));
  const actionsH = actions.length * p.u(52) + Math.max(0, actions.length - 1) * p.u(12);

  /** Body, meta, and actions stacked in a column from y0 to y1. */
  const column = (x: number, w: number, y0: number, y1: number) => {
    let yb = y1;
    for (const s of [...actions].reverse()) {
      p.put(s, { x, y: yb - p.u(52), w, h: p.u(52) });
      yb -= p.u(52) + p.u(12);
    }
    if (actionsH) yb -= p.u(8);
    if (metaH) {
      p.put("detail.meta", { x, y: yb - metaH, w, h: metaH });
      yb -= metaH + p.u(16);
    }
    if (p.has("detail.body")) p.put("detail.body", { x, y: y0, w, h: Math.max(p.textH("body"), yb - y0) });
  };

  if (cls === "desktop" && media) {
    const leftW = safe.w * 0.58;
    const rightX = safe.x + safe.w * 0.62;
    const rightW = safe.w * 0.38;
    const mh = Math.min(leftW * 9 / 16, bottom - y);
    p.put("detail.media", { x: safe.x, y, w: leftW, h: mh });
    const pad = p.u(24);
    p.panel("__panel", { x: rightX, y, w: rightW, h: bottom - y });
    column(rightX + pad, rightW - 2 * pad, y + pad, bottom - pad);
    return;
  }
  const col = cls === "desktop" ? { x: safe.x + safe.w * 0.2, w: safe.w * 0.6 } : { x: safe.x, w: safe.w };
  if (media) {
    const mh = Math.min(col.w * 9 / 16, (bottom - y) * 0.38);
    p.put("detail.media", { x: col.x, y, w: col.w, h: mh });
    y += mh + p.u(24);
  }
  column(col.x, col.w, y, bottom);
}

function grid(p: Plan): void {
  const { cls, safe } = p;
  let y = p.nav();
  if (p.has("grid.title")) {
    const h = p.textH("title");
    p.put("grid.title", { x: safe.x, y, w: safe.w, h });
    y += h + p.u(24);
  }
  const gap = p.u(20);
  const area = { x: safe.x, y, w: safe.w, h: p.bottom() - y };
  if (p.has("grid.aside")) {
    if (cls === "desktop") {
      const aw = safe.w * 0.24;
      p.put("grid.aside", { x: safe.x + safe.w - aw, y, w: aw, h: area.h });
      area.w -= aw + gap;
    } else {
      const ah = p.u(160);
      p.put("grid.aside", { x: safe.x, y: p.bottom() - ah, w: safe.w, h: ah });
      area.h -= ah + gap;
    }
  }
  const cells = p.repeated("grid.cell");
  if (!cells.length) return;
  const n = cells[cells.length - 1]![0];
  const cols = cls === "desktop" ? Math.min(4, n) : cls === "tablet" ? Math.min(2, n) : 1;
  const rows = Math.ceil(n / cols);
  const cw = (area.w - (cols - 1) * gap) / cols;
  const ch = Math.min((area.h - (rows - 1) * gap) / rows, p.u(cls === "phone" ? 132 : 220));
  // Centre the block of cells in the space under the title.
  area.y += Math.max(0, (area.h - (rows * ch + (rows - 1) * gap)) / 2);
  const pad = p.u(20);
  for (const [index, slot] of cells) {
    const i = index - 1;
    const cell = { x: area.x + (i % cols) * (cw + gap), y: area.y + Math.floor(i / cols) * (ch + gap), w: cw, h: ch };
    p.panel(`__cell.${index}`, cell);
    const c = p.get(slot)!;
    const inner = { x: cell.x + pad, y: cell.y + pad, w: cell.w - 2 * pad, h: cell.h - 2 * pad };
    let h = inner.h;
    if (c.kind === "button" || c.kind === "link") h = p.u(52);
    else if (c.kind === "text") h = Math.min(inner.h, p.textH(p.role(c, slot), c.variant === "number" ? 1 : 3));
    else if (["input", "textarea", "select", "slider", "date", "toggle"].includes(c.kind)) h = Math.min(inner.h, p.fieldH(c));
    p.put(slot, { x: inner.x, y: inner.y + (inner.h - h) / 2, w: inner.w, h });
  }
}

function reader(p: Plan): void {
  const { cls, safe } = p;
  const top = p.nav();
  const bottom = p.bottom();
  const pad = p.u(cls === "phone" ? 20 : 32);
  let main = { x: safe.x, w: safe.w };
  let y = top;
  if (cls === "desktop") {
    if (p.has("reader.toc")) {
      const tw = safe.w * 0.24;
      p.put("reader.toc", { x: safe.x, y: top, w: tw, h: bottom - top });
      main = { x: safe.x + safe.w * 0.28, w: safe.w * 0.72 };
    }
  } else if (p.has("reader.toc")) {
    const th = p.u(44) * 3;
    p.put("reader.toc", { x: safe.x, y, w: safe.w, h: th });
    y += th + p.u(20);
  }
  p.panel("__panel", { x: main.x, y, w: main.w, h: bottom - y });
  const ix = main.x + pad;
  const iw = main.w - 2 * pad;
  let iy = y + pad;
  if (p.has("reader.title")) {
    const h = p.textH("title", cls === "phone" ? 2 : 1);
    p.put("reader.title", { x: ix, y: iy, w: iw, h });
    iy += h + p.u(20);
  }
  p.put("reader.body", { x: ix, y: iy, w: iw, h: bottom - pad - iy });
}

function blank(p: Plan): void {
  for (const c of p.frame.components) {
    if (!c.rect) {
      p.diagnostics.push({ code: "missing-rect", component: c.id, message: `"${c.id}" needs a rect in a blank layout` });
      continue;
    }
    const [x, y, w, h] = c.rect;
    p.region(c, { x: x * p.W, y: y * p.H, w: w * p.W, h: h * p.H }, "start");
  }
}

const ARCHETYPE_LAYOUT: Record<Archetype, (p: Plan) => void> = { hero, form, list, detail, grid, reader, blank };

// ── entry point ─────────────────────────────────────────────────────────────

export function resolveArchetype(frame: LayoutFrame): Archetype {
  return frame.layout ?? inferArchetype(frame.components);
}

export function layout(frame: LayoutFrame, cls: ViewportClass, style: StylePack): Wireframe {
  const archetype = resolveArchetype(frame);
  const { slots, issues } = assignSlots(archetype, frame.components);
  const plan = new Plan(cls, frame, slots);
  for (const i of issues) {
    plan.diagnostics.push({ ...i, message: slotMessage(i) });
  }
  ARCHETYPE_LAYOUT[archetype](plan);

  // Regions in tab order: panels first (they sit underneath), then components in slot order.
  const order = new Map([...slots.keys()].map((id, i) => [id, i]));
  const regions = [
    ...plan.regions.filter((r) => r.kind === "panel"),
    ...plan.regions.filter((r) => r.kind !== "panel").sort((a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0)),
  ];

  const s = SAFE_MARGIN;
  const safe: Rect = [s, s, round(1 - 2 * s), round(1 - 2 * s)];
  for (const r of regions) {
    const [x, y, w, h] = r.rect;
    const eps = 1e-3;
    if (archetype !== "blank" && (x < s - eps || y < s - eps || x + w > 1 - s + eps || y + h > 1 - s + eps || h <= 0 || w <= 0)) {
      plan.diagnostics.push({ code: "overflow", component: r.id, message: `"${r.id}" does not fit the safe area on ${cls}` });
    }
  }

  const canvas = CANVAS[cls];
  return {
    canvas,
    viewportClass: cls,
    archetype,
    safe,
    regions,
    svg: wireframeSvg(regions, canvas, style),
    diagnostics: plan.diagnostics,
  };
}

function slotMessage(i: SlotIssue): string {
  switch (i.code) {
    case "unknown-slot": return `"${i.component}" uses slot "${i.slot}", which this archetype does not define`;
    case "slot-taken": return `"${i.component}" uses slot "${i.slot}", which another component already uses`;
    case "no-slot-available": return `no free slot for "${i.component}" in this archetype`;
  }
}
