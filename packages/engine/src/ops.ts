// Ops on documents (05 §6.2): what a handler's assignment or list change does to the document the
// engine holds. Paths name fields, and items of lists of records by key; every value is validated
// against the record's schema before it lands, so a document always fits its record.

import type { Json, JsonObject } from "./intent";
import type { At, Op } from "./protocol";
import { KEY, type PathSegment, type Records } from "./records";

export interface OpContext {
  records: Records;
  /** The record of the document the op applies to. */
  record: string;
  mint: () => string;
  /** A user's own edit, already checked for shape: kept even when it breaks a constraint, which
   *  the frame reports as invalid instead (the user is still typing). */
  edit?: boolean;
}

export type Applied = { ok: true } | { ok: false; reason: string };

const isObject = (v: unknown): v is JsonObject => typeof v === "object" && v !== null && !Array.isArray(v);

function itemIndex(list: Json[], key: string): number {
  return list.findIndex((item) => isObject(item) && item[KEY] === key);
}

/** The container a path leads into, walking all but its last segment. */
function walk(root: Json, path: PathSegment[]): Json | undefined {
  let cur: Json | undefined = root;
  for (const seg of path) {
    if (cur === undefined) return undefined;
    if (typeof seg === "string") {
      if (!isObject(cur) || !Object.hasOwn(cur, seg)) return undefined;
      cur = cur[seg];
    } else {
      if (!Array.isArray(cur)) return undefined;
      const i = itemIndex(cur, seg.key);
      cur = i < 0 ? undefined : cur[i];
    }
  }
  return cur;
}

function position(list: Json[], at: At | undefined): number {
  if (at === undefined || at === "end") return list.length;
  if (at === "start") return 0;
  const anchor = "before" in at ? at.before : at.after;
  const i = itemIndex(list, anchor);
  if (i < 0) return list.length;
  return "before" in at ? i : i + 1;
}

function findItem(list: Json[], key: string | undefined, id: string | undefined, idField: string | undefined): number {
  if (key !== undefined) {
    const i = itemIndex(list, key);
    if (i >= 0) return i;
  }
  if (id !== undefined && idField) {
    return list.findIndex((item) => isObject(item) && item[idField] !== null && String(item[idField]) === id);
  }
  return -1;
}

/** Applies one op to `doc` in place. Nothing changes when it does not apply. */
export function applyOp(doc: Json, op: Op, ctx: OpContext): Applied {
  const { records, record } = ctx;
  const path = op.path as PathSegment[];
  if (path.length === 0) return { ok: false, reason: "an empty path" };
  const located = records.locate(record, path);
  if (!located) return { ok: false, reason: `${record} has no ${describe(path)}` };
  if (records.isSecret(located.record, located.field)) return { ok: false, reason: "documents never hold secrets" };

  if (op.op === "set") {
    if (op.value === undefined) return { ok: false, reason: "set without a value" };
    // Keys go into the op's own value, so applying it again (over a newer base) keys items the same.
    const value = op.value as Json;
    const last = path[path.length - 1]!;
    const itemRecord = located.item ? located.kind.item?.record : undefined;
    if (typeof last === "string") keyValue(ctx, located.record, located.field, value);
    else if (isObject(value)) {
      value[KEY] = last.key;
      if (itemRecord) records.assignKeys(itemRecord, value, ctx.mint);
    }
    const problems = ctx.edit
      ? []
      : located.item
        ? records.validateItem(located.record, located.field, value)
        : records.validateField(located.record, located.field, value);
    if (problems.length) return { ok: false, reason: `${describe(path)}: ${problems[0]}` };
    const parent = walk(doc, path.slice(0, -1));
    if (typeof last === "string") {
      if (!isObject(parent)) return { ok: false, reason: `${describe(path)} is not in the document` };
      parent[last] = structuredClone(value);
    } else {
      if (!Array.isArray(parent)) return { ok: false, reason: `${describe(path)} is not in the document` };
      const i = itemIndex(parent, last.key);
      if (i < 0) return { ok: false, reason: `no item ${last.key}` };
      parent[i] = structuredClone(value);
    }
    return { ok: true };
  }

  // insert, remove, and replace work on a list: the path names the list field.
  if (located.item || located.kind.type !== "collection") return { ok: false, reason: `${describe(path)} is not a list` };
  const holder = walk(doc, path.slice(0, -1));
  const field = path[path.length - 1] as string;
  if (!isObject(holder)) return { ok: false, reason: `${describe(path)} is not in the document` };
  const current = holder[field];
  if (current !== undefined && current !== null && !Array.isArray(current)) return { ok: false, reason: `${describe(path)} is not a list` };
  const list: Json[] = Array.isArray(current) ? current : [];
  const itemRecord = located.kind.item?.type === "record" ? located.kind.item.record : undefined;
  if (!itemRecord) return { ok: false, reason: `${describe(path)} holds plain values, which change as a whole` };
  const idField = records.idField(itemRecord);

  if (op.op === "remove") {
    const i = findItem(list, op.key, op.id, idField);
    if (i < 0) return { ok: false, reason: `no item ${op.key ?? op.id} in ${describe(path)}` };
    list.splice(i, 1);
    return { ok: true };
  }
  if (op.value === undefined) return { ok: false, reason: `${op.op} without a value` };
  const value = op.value as Json;
  if (!isObject(value)) return { ok: false, reason: "an item of a list of records is an object" };
  records.assignKeys(itemRecord, value, ctx.mint);
  const problems = records.validateItem(located.record, located.field, value);
  if (problems.length) return { ok: false, reason: `${describe(path)}: ${problems[0]}` };

  if (op.op === "insert") {
    if (itemIndex(list, op.key) >= 0) return { ok: false, reason: `${describe(path)} already has an item ${op.key}` };
    value[KEY] = op.key;
    list.splice(position(list, op.at), 0, structuredClone(value));
    if (list !== current) holder[field] = list;
    return { ok: true };
  }
  const i = findItem(list, op.key, op.id, idField);
  if (i < 0) return { ok: false, reason: `no item ${op.key ?? op.id} in ${describe(path)}` };
  const replaced = structuredClone(value);
  replaced[KEY] = (list[i] as JsonObject)[KEY] as string;
  list[i] = replaced;
  return { ok: true };
}

/** Keys the record items of a value that lands in a field: a nested record, or a list of records. */
function keyValue(ctx: OpContext, record: string, field: string, value: Json): void {
  const kind = ctx.records.kind(record, field);
  if (!kind || value === null) return;
  if (kind.type === "record" && kind.record) ctx.records.assignKeys(kind.record, value, ctx.mint);
  else if (kind.type === "collection" && kind.item?.type === "record" && kind.item.record && Array.isArray(value)) {
    for (const item of value) ctx.records.keyItem(kind.item.record, item, ctx.mint);
  }
}

export function describe(path: PathSegment[]): string {
  return path.map((s) => (typeof s === "string" ? s : `[${s.key}]`)).join(".");
}
