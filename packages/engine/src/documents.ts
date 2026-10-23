// Documents (05 §6.2): the state the engine holds. A shown document with a `vt.Id` is held once,
// keyed by its record and id, and shared by every session that holds it; a shown document without
// one, and every edited document, is the session's own. Documents live in memory for as long as a
// reel holds them, and are never persisted or logged (05 §12).
//
// A handler's changes are shown at once and marked tentative: each document keeps the value they
// were confirmed into and, on top of it, the tentative layers of the decisions still running, in
// the order they arrived. What a reader sees is the confirmed value with every layer applied. A
// decision that returns folds its layers into the confirmed value; one that raises or rejects
// drops them; and every change, from anywhere, re-applies the layers still open on top, so two
// decisions and the app's own changes can interleave without losing one another.

import type { Json } from "./intent";
import type { Logger } from "./log";
import { applyOp, describe } from "./ops";
import type { DocRef, Op } from "./protocol";
import { type PathSegment, type Records, stripKeys } from "./records";

export type DocState = "confirmed" | "tentative" | "rolledback";

interface Layer {
  decision: string;
  ops: Op[];
}

export interface Doc {
  ref: DocRef;
  record: string;
  /** The value every confirmed change has been folded into. */
  confirmed: Json;
  /** What readers see: the confirmed value with the open decisions' layers applied. */
  value: Json;
  /** Tentative changes of decisions still running, in the order they arrived. */
  layers: Layer[];
  /** Who holds it: one entry per tape visit of a reel that has it (`<session>:<visit>`). */
  holders: Set<string>;
  /** Grows with every change a reader can see, tentative or not. */
  version: number;
}

export interface DocChange {
  doc: Doc;
  state: DocState;
  /** The ops that changed what readers see (none for a confirm or a rollback, which re-apply). */
  ops: Op[];
  /** The decision the change belongs to. */
  decision?: string;
  /** The whole value was replaced: a reload of a held document. */
  reset?: true;
}

export type DocListener = (change: DocChange) => void;

export function refKey(ref: DocRef): string {
  return "id" in ref ? `${ref.record}#${ref.id}` : `~${ref.local}`;
}

export class DocumentStore {
  private readonly docs = new Map<string, Doc>();
  /** The documents each open decision has layers on. */
  private readonly decisions = new Map<string, Set<string>>();
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

  /** What a reader sees, without the engine's item keys. */
  read(ref: DocRef): Json | undefined {
    const d = this.get(ref);
    return d === undefined ? undefined : stripKeys(d.value);
  }

  /** Whether a document carries changes of decisions still running. */
  isTentative(ref: DocRef): boolean {
    return (this.get(ref)?.layers.length ?? 0) > 0;
  }

  onChange(listener: DocListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(change: DocChange): void {
    for (const l of this.listeners) l(change);
  }

  // ── holding ────────────────────────────────────────────────────────────────

  private create(ref: DocRef, record: string, value: Json, holder: string): Doc {
    const doc: Doc = { ref, record, confirmed: value, value: structuredClone(value), layers: [], holders: new Set([holder]), version: 0 };
    this.docs.set(refKey(ref), doc);
    return doc;
  }

  /** Holds a loaded document for `holder`: shared by its id when its record has one and the value
   *  sets it (and `own` is false), else the holder's own. A shared document already held is
   *  refreshed with the loaded value, since the app is the source of truth. */
  load(record: string, value: Json, holder: string, own = false): DocRef {
    const idField = this.records.idField(record);
    const id = idField && typeof value === "object" && value !== null && !Array.isArray(value) ? value[idField] : undefined;
    if (!own && (typeof id === "string" || typeof id === "number")) {
      const ref: DocRef = { record, id: String(id) };
      const keyed = structuredClone(value);
      this.records.assignKeys(record, keyed, this.mint);
      const known = this.get(ref);
      if (known) {
        known.holders.add(holder);
        this.refresh(known, keyed);
      } else {
        this.create(ref, record, keyed, holder);
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
    this.create(ref, record, keyed, holder);
    return ref;
  }

  /** Replaces a held document's confirmed value with a newer one from the app; open layers stay on top. */
  private refresh(doc: Doc, value: Json): void {
    if (JSON.stringify(stripKeys(doc.confirmed)) === JSON.stringify(stripKeys(value))) return;
    doc.confirmed = value;
    this.recompute(doc);
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

  private applyAll(doc: Doc, target: Json, ops: Op[], edit: boolean, quiet = false): Op[] {
    const applied: Op[] = [];
    for (const op of ops) {
      const r = applyOp(target, op, { records: this.records, record: doc.record, mint: this.mint, edit });
      if (r.ok) applied.push(op);
      else if (!quiet) this.log.warn("an op was refused", { record: doc.record, op: op.op, path: describe(op.path as PathSegment[]), reason: r.reason });
    }
    return applied;
  }

  /** The visible value again: the confirmed value with every open layer on top. */
  private recompute(doc: Doc): void {
    const value = structuredClone(doc.confirmed);
    for (const layer of doc.layers) this.applyAll(doc, value, layer.ops, false, true);
    doc.value = value;
    doc.version += 1;
  }

  /** A user's edit of a field (a local change): confirmed at once, without the app. */
  edit(ref: DocRef, ops: Op[]): Op[] {
    return this.confirmNow(ref, ops, true);
  }

  /** The app's changes outside any decision (`vt.docs` from a service): confirmed at once. */
  apply(ref: DocRef, ops: Op[]): Op[] {
    return this.confirmNow(ref, ops, false);
  }

  private confirmNow(ref: DocRef, ops: Op[], edit: boolean): Op[] {
    const doc = this.get(ref);
    if (!doc) {
      this.log.debug("a change to a document nobody holds was dropped", { record: ref.record });
      return [];
    }
    const applied = this.applyAll(doc, doc.confirmed, ops, edit);
    if (!applied.length) return applied;
    if (doc.layers.length) this.recompute(doc);
    else {
      this.applyAll(doc, doc.value, applied, edit, true);
      doc.version += 1;
    }
    this.notify({ doc, state: "confirmed", ops: applied });
    return applied;
  }

  /** A running decision's changes: shown at once, on top of everything else, until it ends. */
  tentative(decision: string, ref: DocRef, ops: Op[]): Op[] {
    const doc = this.get(ref);
    if (!doc) {
      this.log.debug("a tentative change to a document nobody holds was dropped", { record: ref.record });
      return [];
    }
    const applied = this.applyAll(doc, doc.value, ops, false);
    if (!applied.length) return applied;
    const last = doc.layers[doc.layers.length - 1];
    if (last && last.decision === decision) last.ops.push(...applied);
    else doc.layers.push({ decision, ops: applied });
    doc.version += 1;
    let touched = this.decisions.get(decision);
    if (!touched) this.decisions.set(decision, (touched = new Set()));
    touched.add(refKey(ref));
    this.notify({ doc, state: "tentative", ops: applied, decision });
    return applied;
  }

  /** The decision returned: its changes become confirmed, in the order they were made. */
  confirm(decision: string): void {
    this.end(decision, true);
  }

  /** The decision raised or rejected: its changes are taken back, everywhere they were shown. */
  rollback(decision: string): void {
    this.end(decision, false);
  }

  private end(decision: string, keep: boolean): void {
    const touched = this.decisions.get(decision);
    this.decisions.delete(decision);
    for (const key of touched ?? []) {
      const doc = this.docs.get(key);
      if (!doc) continue;
      const mine = doc.layers.filter((l) => l.decision === decision);
      if (!mine.length) continue;
      doc.layers = doc.layers.filter((l) => l.decision !== decision);
      if (keep) for (const layer of mine) this.applyAll(doc, doc.confirmed, layer.ops, false, true);
      this.recompute(doc);
      this.notify({ doc, state: keep ? "confirmed" : "rolledback", ops: [], decision });
    }
  }

  /** Every document's visible value, for tests: never logged. */
  snapshot(): Record<string, Json> {
    const out: Record<string, Json> = {};
    for (const [k, d] of this.docs) out[k] = stripKeys(d.value);
    return out;
  }
}
