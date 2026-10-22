// The content layer (spec §8): every fact and control, resolved from the frame
// spec and the reel's data, placed on the wireframe's regions. Also the value
// checks the engine applies to incoming events (spec §10).

import {
  type Component, type Content, type Data, type Frame, type ListItem, type SelectOption, type Wireframe, MAX_VALUE_BYTES,
  getPath, isBind,
} from "@videotape/core";

function asText(v: unknown): string {
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return "";
}

/** Only same-origin paths, https, and inline images may reach an `src`. */
export function safeSrc(v: unknown): string | undefined {
  if (typeof v !== "string") return undefined;
  if (v.startsWith("/") && !v.startsWith("//")) return v;
  if (v.startsWith("https://") || v.startsWith("data:image/")) return v;
  return undefined;
}

function asItems(v: unknown): ListItem[] {
  if (!Array.isArray(v)) return [];
  return v.flatMap((x) =>
    x && typeof x === "object" && typeof x.id === "string" && typeof x.label === "string"
      ? [{ id: x.id, label: x.label, ...(typeof x.meta === "string" ? { meta: x.meta } : {}) }]
      : []);
}

function asOptions(v: unknown): SelectOption[] {
  if (!Array.isArray(v)) return [];
  return v.flatMap((x) =>
    x && typeof x === "object" && typeof x.value === "string" && typeof x.label === "string" ? [{ value: x.value, label: x.label }] : []);
}

export function listItems(c: Component & { kind: "list" }, data: Data): ListItem[] {
  return c.bind ? asItems(getPath(data, c.bind)) : c.items ?? [];
}

export function selectOptions(c: Component & { kind: "select" }, data: Data): SelectOption[] {
  return isBind(c.options) ? asOptions(getPath(data, c.options.bind)) : c.options;
}

function contentFor(c: Component, data: Data): Partial<Content> {
  const bound = (path: string | undefined) => (path ? getPath(data, path) : undefined);
  switch (c.kind) {
    case "text":
      return { value: c.bind ? asText(bound(c.bind)) : c.value ?? "", ...(c.variant ? { variant: c.variant } : {}) };
    case "image": {
      const src = safeSrc(c.bind ? bound(c.bind) : c.src);
      return { ...(src ? { src } : {}), alt: c.alt ?? "" };
    }
    case "media": {
      const src = safeSrc(c.bind ? bound(c.bind) : c.src);
      return { ...(src ? { src } : {}), media: c.media ?? "video" };
    }
    case "button":
      return { label: c.label };
    case "link":
      return { label: c.label };
    case "input": {
      const type = c.type ?? "text";
      const out: Partial<Content> = { label: c.label, inputType: type, commit: c.commit ?? "submit" };
      if (c.placeholder) out.placeholder = c.placeholder;
      // A secret is never sent back to the player (spec §10).
      if (type !== "secret" && c.bind) out.value = asText(bound(c.bind));
      return out;
    }
    case "textarea":
      return { label: c.label, commit: c.commit ?? "submit", ...(c.placeholder ? { placeholder: c.placeholder } : {}),
        ...(c.bind ? { value: asText(bound(c.bind)) } : {}) };
    case "select":
      return { label: c.label, commit: c.commit ?? "submit", options: selectOptions(c, data), ...(c.bind ? { value: asText(bound(c.bind)) } : {}) };
    case "toggle":
      return { label: c.label, commit: c.commit ?? "submit", value: c.bind ? bound(c.bind) === true : false };
    case "slider": {
      const v = bound(c.bind);
      return {
        label: c.label, commit: c.commit ?? "submit", min: c.min ?? 0, max: c.max ?? 100, step: c.step ?? 1,
        ...(typeof v === "number" ? { value: v } : {}),
      };
    }
    case "date":
      return { label: c.label, commit: c.commit ?? "submit", ...(c.bind ? { value: asText(bound(c.bind)) } : {}) };
    case "list":
      return { items: listItems(c, data), ...(c.label ? { label: c.label } : {}) };
  }
}

/** Content nodes in the wireframe's tab order. */
export function buildContent(frame: Frame, wf: Wireframe, data: Data): Content[] {
  const byId = new Map(frame.components.map((c) => [c.id, c]));
  const out: Content[] = [];
  for (const r of wf.regions) {
    if (r.kind === "panel") continue;
    const c = byId.get(r.id);
    if (!c) continue;
    const node: Content = { id: c.id, kind: c.kind, rect: r.rect, ...contentFor(c, data) };
    if (r.type) node.type = r.type;
    if (r.labelSize) node.labelSize = r.labelSize;
    if (r.emphasis) node.emphasis = r.emphasis;
    if (c.a11y) node.a11y = c.a11y;
    out.push(node);
  }
  return out;
}

const DYNAMIC: Array<keyof Content> = ["value", "items", "options", "src", "alt", "label"];

/** Changed fields per component, for a `patch` after `stay`. */
export function diffContent(before: Content[], after: Content[]): Array<Partial<Content> & { id: string }> {
  const prev = new Map(before.map((c) => [c.id, c]));
  const out: Array<Partial<Content> & { id: string }> = [];
  for (const c of after) {
    const p = prev.get(c.id);
    const changed: Partial<Content> & { id: string } = { id: c.id };
    let any = false;
    for (const k of DYNAMIC) {
      if (JSON.stringify(p?.[k]) !== JSON.stringify(c[k])) {
        (changed as Record<string, unknown>)[k] = c[k] ?? null;
        any = true;
      }
    }
    if (any) out.push(changed);
  }
  return out;
}

/** Does `v` fit what component `c` can produce? */
export function validValue(c: Component, v: unknown, data: Data): boolean {
  switch (c.kind) {
    case "input": case "textarea":
      return typeof v === "string" && Buffer.byteLength(v) <= MAX_VALUE_BYTES;
    case "select":
      return typeof v === "string" && (v === "" || selectOptions(c, data).some((o) => o.value === v));
    case "toggle":
      return typeof v === "boolean";
    case "slider":
      return typeof v === "number" && Number.isFinite(v) && v >= (c.min ?? 0) && v <= (c.max ?? 100);
    case "date":
      return typeof v === "string" && (v === "" || /^\d{4}-\d{2}-\d{2}$/.test(v));
    case "list":
      return typeof v === "string" && listItems(c, data).some((i) => i.id === v);
    default:
      return v === undefined;
  }
}
