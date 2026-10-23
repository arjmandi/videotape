// Records: the typed models an intent carries (05 §6.1), as the engine uses them. The engine
// validates what users type and what handlers write against them, finds a document's identity
// (its `vt.Id` field), keeps secrets apart, and keys the items of lists of records.

import type { ValidateFunction } from "ajv";
import { Ajv2020 } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import type { Intent, Json, JsonObject, Kind, PropertySchema, RecordSchema } from "./intent";

/** Each record item of a list carries its key under this name while the engine holds it (05 §6.1:
 *  `vt.Id` keys list items; items without one are keyed by the engine, or by the SDK that added them). */
export const KEY = "@key";

export class Records {
  private readonly ajv: Ajv2020;
  private readonly compiled = new Map<string, ValidateFunction>();

  constructor(readonly intent: Intent) {
    this.ajv = new Ajv2020({ strict: false, allErrors: true });
    addFormats(this.ajv);
    this.ajv.addFormat("password", true);
    // The intent's records and types, as one schema document their `#/records/...` refs resolve in.
    this.ajv.addSchema({ $id: "vt:intent", records: intent.records, types: intent.types } as object);
  }

  has(record: string): boolean {
    return record in this.intent.records;
  }

  schema(record: string): RecordSchema {
    const r = this.intent.records[record];
    if (!r) throw new Error(`no record ${record}`);
    return r;
  }

  /** The name of the record's `vt.Id` field, if it has one. */
  idField(record: string): string | undefined {
    return this.intent.records[record]?.["x-vt"]?.id;
  }

  property(record: string, field: string): PropertySchema | undefined {
    const props = this.intent.records[record]?.properties;
    return props && Object.hasOwn(props, field) ? props[field] : undefined;
  }

  kind(record: string, field: string): (Kind & { [option: string]: unknown }) | undefined {
    return this.property(record, field)?.["x-vt"];
  }

  fields(record: string): string[] {
    return Object.keys(this.intent.records[record]?.properties ?? {});
  }

  isSecret(record: string, field: string): boolean {
    return this.kind(record, field)?.type === "secret";
  }

  secretFields(record: string): string[] {
    return this.fields(record).filter((f) => this.isSecret(record, f));
  }

  /** A document of this record from its defaults; required fields without one are left out. */
  defaults(record: string): JsonObject {
    const out: JsonObject = {};
    for (const [field, prop] of Object.entries(this.schema(record).properties ?? {})) {
      if (prop.default !== undefined) out[field] = structuredClone(prop.default);
    }
    return out;
  }

  // ── validation ─────────────────────────────────────────────────────────────

  private validator(pointer: string): ValidateFunction {
    const known = this.compiled.get(pointer);
    if (known) return known;
    const v = this.ajv.compile({ $ref: `vt:intent#${pointer}` });
    this.compiled.set(pointer, v);
    return v;
  }

  private run(pointer: string, value: unknown): string[] {
    const v = this.validator(pointer);
    if (v(stripKeys(value))) return [];
    return (v.errors ?? []).map((e) => `${e.instancePath || "/"} ${e.message ?? "is invalid"}`);
  }

  /** Problems with a whole document of this record; empty when it is valid. */
  validate(record: string, value: unknown): string[] {
    return this.run(`/records/${escape(record)}`, value);
  }

  /** Problems with one field's value. */
  validateField(record: string, field: string, value: unknown): string[] {
    return this.run(`/records/${escape(record)}/properties/${escape(field)}`, value);
  }

  /** Problems with one item of a list field. */
  validateItem(record: string, field: string, value: unknown): string[] {
    const prop = this.property(record, field);
    if (!prop) return [`${record} has no field ${field}`];
    const base = `/records/${escape(record)}/properties/${escape(field)}`;
    if (prop.items !== undefined) return this.run(`${base}/items`, value);
    const branches = Array.isArray(prop.anyOf) ? (prop.anyOf as Array<{ items?: unknown }>) : [];
    const i = branches.findIndex((b) => b.items !== undefined);
    if (i < 0) return [`${record}.${field} is not a list`];
    return this.run(`${base}/anyOf/${i}/items`, value);
  }

  // ── keys ───────────────────────────────────────────────────────────────────

  /**
   * Gives every record item of every list in `value` a key, in place: its `vt.Id` when it has one,
   * or a fresh one from `mint`. Items that carry a key keep it.
   */
  assignKeys(record: string, value: Json, mint: () => string): void {
    if (typeof value !== "object" || value === null || Array.isArray(value)) return;
    for (const field of this.fields(record)) {
      const kind = this.kind(record, field);
      const child = value[field];
      if (!kind || child === undefined || child === null) continue;
      if (kind.type === "record" && kind.record) this.assignKeys(kind.record, child, mint);
      else if (kind.type === "collection" && kind.item?.type === "record" && kind.item.record && Array.isArray(child)) {
        for (const item of child) this.keyItem(kind.item.record, item, mint);
      }
    }
  }

  /** Keys one record item of a list, and the lists inside it. */
  keyItem(record: string, item: Json, mint: () => string): void {
    if (typeof item !== "object" || item === null || Array.isArray(item)) return;
    if (typeof item[KEY] !== "string") {
      const idField = this.idField(record);
      const id = idField ? item[idField] : undefined;
      item[KEY] = typeof id === "string" || typeof id === "number" ? String(id) : mint();
    }
    this.assignKeys(record, item, mint);
  }

  /**
   * Walks a path of field names and `{key}` segments from a record and says what it reaches: the
   * record that holds the last field, the field, and its kind. `undefined` when the path does not fit
   * the record's shape.
   */
  locate(record: string, path: PathSegment[]): Located | undefined {
    let current = record;
    let i = 0;
    while (i < path.length) {
      const seg = path[i];
      if (typeof seg !== "string") return undefined;
      const kind = this.kind(current, seg);
      if (!kind) return undefined;
      const last = i === path.length - 1;
      if (last) return { record: current, field: seg, kind, item: false };
      if (kind.type === "record" && kind.record) {
        current = kind.record;
        i += 1;
        continue;
      }
      if (kind.type === "collection" && typeof path[i + 1] === "object") {
        if (i + 1 === path.length - 1) return { record: current, field: seg, kind, item: true };
        if (kind.item?.type !== "record" || !kind.item.record) return undefined;
        current = kind.item.record;
        i += 2;
        continue;
      }
      return undefined;
    }
    return undefined;
  }
}

export type PathSegment = string | { key: string };

export interface Located {
  record: string;
  field: string;
  kind: Kind;
  /** The path ends at an item of the list `field`, rather than at the field. */
  item: boolean;
}

function escape(token: string): string {
  return token.replace(/~/g, "~0").replace(/\//g, "~1");
}

/** A deep copy of a value without the engine's item keys. */
export function stripKeys<T>(value: T): T {
  if (Array.isArray(value)) return value.map(stripKeys) as T;
  if (typeof value === "object" && value !== null) {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value)) if (k !== KEY) out[k] = stripKeys(v);
    return out as T;
  }
  return value;
}
