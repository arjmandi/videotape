// Documents (05 §6.2): the state the engine holds. A shown document with a `vt.Id` is held once,
// keyed by its record and id, and shared by every session that holds it; a shown document without
// one, and every edited document, is the session's own. Documents live in memory for as long as a
// reel holds them, and are never persisted or logged (05 §12).

import type { Json } from "./intent";
import type { Logger } from "./log";
import { applyOp, describe } from "./ops";
import type { DocRef, Op } from "./protocol";
import { type PathSegment, type Records, stripKeys } from "./records";

export interface Doc {
  ref: DocRef;
  record: string;
  /** The value every change has been confirmed into. */
  value: Json;
  /** Who holds it: one entry per tape visit of a reel that has it. */
  holders: Set<string>;
  version: number;
}

export interface DocChange {
  doc: Doc;
  state: "confirmed";
  ops: Op[];
  /** The whole value was replaced: a reload of a held document. */
  reset?: true;
  /** The decision whose changes these are, if a decision made them. */
  decision?: string;
}

export type DocListener = (change: DocChange) => void;

export function refKey(ref: DocRef): string {
  return "id" in ref ? `${ref.record}#${ref.id}` : `~${ref.local}`;
}

export class DocumentStore {
  private readonly docs = new Map<string, Doc>();
  private readonly buffers = new Map<string, Array<{ key: string; ops: Op[] }>>();
  private readonly listeners = new Set<DocListener>();
  private minted = 0;
  private locals = 0;

  constructor(private readonly records: Records, private readonly log: Logger) {}

  /** A fresh key for a list item the engine keys. */
  mint = (): string => `~e${++this.minted}`;

  get size(): number {
    return this.docs.size;
  }

  get(ref: DocRef): Doc | undefined {
    return this.docs.get(refKey(ref));
  }

  /** The document's value without the engine's item keys, as a reader sees it. */
  read(ref: DocRef): Json | undefined {
    const d = this.get(ref);
    return d === undefined ? undefined : stripKeys(d.value);
  }

  onChange(listener: DocListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(change: DocChange): void {
    for (const l of this.listeners) l(change);
  }

  // ── holding ────────────────────────────────────────────────────────────────

  /** Holds a loaded document for `holder`: shared by its id when its record has one and the value
   *  sets it (and `own` is false), else the holder's own. A shared document already held is
   *  refreshed with the loaded value, since the app is the source of truth. */
  load(record: string, value: Json, holder: string, own = false): DocRef {
    const idField = this.records.idField(record);
    const id = idField && typeof value === "object" && value !== null && !Array.isArray(value) ? value[idField] : undefined;
    if (!own && (typeof id === "string" || typeof id === "number")) {
      const ref: DocRef = { record, id: String(id) };
      const known = this.get(ref);
      const keyed = structuredClone(value);
      this.records.assignKeys(record, keyed, this.mint);
      if (known) {
        known.holders.add(holder);
        this.refresh(known, keyed);
      } else {
        this.docs.set(refKey(ref), { ref, record, value: keyed, holders: new Set([holder]), version: 0 });
      }
      return ref;
    }
    return this.own(record, value, holder);
  }

  /** A new document of the holder's own. Lists (a frame that shows `list[Deal]`) are own documents too. */
  own(record: string, value: Json, holder: string): DocRef {
    const ref: DocRef = { record, local: `d${++this.locals}` };
    const keyed = structuredClone(value);
    if (Array.isArray(keyed)) {
      const item = record.endsWith("[]") ? record.slice(0, -2) : record;
      for (const v of keyed) this.records.keyItem(item, v, this.mint);
    } else {
      this.records.assignKeys(record, keyed, this.mint);
    }
    this.docs.set(refKey(ref), { ref, record, value: keyed, holders: new Set([holder]), version: 0 });
    return ref;
  }

  /** Replaces a held document's value with a newer one from the app. */
  protected refresh(doc: Doc, value: Json): void {
    if (JSON.stringify(stripKeys(doc.value)) === JSON.stringify(stripKeys(value))) return;
    doc.value = value;
    doc.version += 1;
    this.notify({ doc, state: "confirmed", ops: [], reset: true });
  }

  hold(ref: DocRef, holder: string): void {
    this.get(ref)?.holders.add(holder);
  }

  /** Lets go of one document. */
  drop(ref: DocRef, holder: string): void {
    const key = refKey(ref);
    const d = this.docs.get(key);
    if (d && d.holders.delete(holder) && d.holders.size === 0) this.docs.delete(key);
  }

  /** Lets go of every document `holder` holds; a document nobody holds is dropped. */
  release(holder: string): void {
    for (const [key, d] of this.docs) {
      if (d.holders.delete(holder) && d.holders.size === 0) this.docs.delete(key);
    }
  }

  // ── changing ───────────────────────────────────────────────────────────────

  /** A user's edit of a field (a local change): applied at once, confirmed, without the app. */
  edit(ref: DocRef, ops: Op[]): Op[] {
    return this.apply(ref, ops, undefined, true);
  }

  /** Applies ops at once, confirmed: the app's changes outside a decision, or a decision's on confirm. */
  apply(ref: DocRef, ops: Op[], decision?: string, edit = false): Op[] {
    const doc = this.get(ref);
    if (!doc) {
      this.log.debug("a change to a document nobody holds was dropped", { record: ref.record });
      return [];
    }
    const applied: Op[] = [];
    for (const op of ops) {
      const r = applyOp(doc.value, op, { records: this.records, record: doc.record, mint: this.mint, edit });
      if (r.ok) applied.push(op);
      else this.log.warn("an op was refused", { record: doc.record, op: op.op, path: describe(op.path as PathSegment[]), reason: r.reason });
    }
    if (applied.length) {
      doc.version += 1;
      this.notify({ doc, state: "confirmed", ops: applied, ...(decision ? { decision } : {}) });
    }
    return applied;
  }

  /** Changes a decision makes: kept until it returns (confirm) or fails (roll back). */
  tentative(decision: string, ref: DocRef, ops: Op[]): void {
    let buffer = this.buffers.get(decision);
    if (!buffer) this.buffers.set(decision, (buffer = []));
    buffer.push({ key: refKey(ref), ops });
  }

  confirm(decision: string): void {
    const buffer = this.buffers.get(decision) ?? [];
    this.buffers.delete(decision);
    for (const { key, ops } of buffer) {
      const doc = this.docs.get(key);
      if (doc) this.apply(doc.ref, ops, decision);
    }
  }

  rollback(decision: string): void {
    this.buffers.delete(decision);
  }

  /** Every document's value, for tests: never logged. */
  snapshot(): Record<string, Json> {
    const out: Record<string, Json> = {};
    for (const [k, d] of this.docs) out[k] = stripKeys(d.value);
    return out;
  }
}
