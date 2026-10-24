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
  /** Grows with every change to what readers see, tentative or not. */
  version: number;
  /** Grows with every change to the confirmed value: the app's mirror holds confirmed values (Q68). */
  cversion: number;
}

/** Where a change came from: the app (a decision, or `vt.docs`), a user's edit, or the engine itself
 *  (a rollback, a confirm that reorders layers, a reload). */
export type Origin = "app" | "user" | "engine";

export interface DocChange {
  doc: Doc;
  state: DocState;
  origin: Origin;
  /** The version before the change; equal to `doc.version` when readers see no difference. */
  from: number;
  /** The ops that took the value from `from` to `doc.version`, unless `whole`. */
  ops: Op[];
  /** The value changed in a way no ops describe (a rollback, a reload): send it whole. */
  whole?: true;
  /** The decision the change belongs to. */
  decision?: string;
}

export type DocListener = (change: DocChange) => void;
export type DropListener = (ref: DocRef) => void;

/** A change to a document's confirmed value: ops from `from` to `doc.cversion`, or the whole value. */
export interface ConfirmedChange {
  doc: Doc;
  from: number;
  ops: Op[];
  whole?: true;
  /** The app's own change outside any decision, which its mirror applied as it made it. */
  origin: Origin;
}

export type ConfirmedListener = (change: ConfirmedChange) => void;

export function refKey(ref: DocRef): string {
  return "id" in ref ? `${ref.record}#${ref.id}` : `~${ref.local}`;
}

export class DocumentStore {
  private readonly docs = new Map<string, Doc>();
  /** The documents each open decision has layers on. */
  private readonly decisions = new Map<string, Set<string>>();
  private readonly listeners = new Set<DocListener>();
  private readonly dropListeners = new Set<DropListener>();
  private readonly confirmedListeners = new Set<ConfirmedListener>();
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

  /** Hears of every change to a confirmed value: what keeps the app's mirror current. */
  onConfirmed(listener: ConfirmedListener): () => void {
    this.confirmedListeners.add(listener);
    return () => this.confirmedListeners.delete(listener);
  }

  private confirmed(change: Omit<ConfirmedChange, "from">): void {
    const from = change.doc.cversion;
    change.doc.cversion += 1;
    for (const l of this.confirmedListeners) l({ ...change, from });
  }

  /** Hears of every document that is dropped, because its last holder let go. */
  onDrop(listener: DropListener): () => void {
    this.dropListeners.add(listener);
    return () => this.dropListeners.delete(listener);
  }

  private notify(change: DocChange): void {
    for (const l of this.listeners) l(change);
  }

  private forget(key: string, doc: Doc): void {
    this.docs.delete(key);
    for (const l of this.dropListeners) l(doc.ref);
  }

  // ── holding ────────────────────────────────────────────────────────────────

  private create(ref: DocRef, record: string, value: Json, holder: string): Doc {
    const doc: Doc = { ref, record, confirmed: value, value: structuredClone(value), layers: [], holders: new Set([holder]), version: 0, cversion: 0 };
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
    this.confirmed({ doc, ops: [], whole: true, origin: "engine" });
    const from = doc.version;
    if (this.recompute(doc)) this.notify({ doc, state: "confirmed", origin: "engine", from, ops: [], whole: true });
  }

  hold(ref: DocRef, holder: string): void {
    this.get(ref)?.holders.add(holder);
  }

  /** Lets go of one document. */
  drop(ref: DocRef, holder: string): void {
    const key = refKey(ref);
    const d = this.docs.get(key);
    if (d && d.holders.delete(holder) && d.holders.size === 0) this.forget(key, d);
  }

  /** Lets go of every document `holder` holds; a document nobody holds is dropped. */
  release(holder: string): void {
    for (const [key, d] of this.docs) {
      if (d.holders.delete(holder) && d.holders.size === 0) this.forget(key, d);
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

  /** The visible value again: the confirmed value with every open layer on top. Says whether readers see a difference. */
  private recompute(doc: Doc): boolean {
    const value = structuredClone(doc.confirmed);
    for (const layer of doc.layers) this.applyAll(doc, value, layer.ops, false, true);
    const changed = JSON.stringify(value) !== JSON.stringify(doc.value);
    doc.value = value;
    if (changed) doc.version += 1;
    return changed;
  }

  /** A user's edit of a field (a local change): confirmed at once, without the app. */
  edit(ref: DocRef, ops: Op[]): Op[] {
    return this.confirmNow(ref, ops, true);
  }

  /** The app's changes outside any decision (`vt.docs`, and work a handler left running): confirmed at
   *  once. `origin` is "engine" for changes the app did not make through its mirror (a late decision). */
  apply(ref: DocRef, ops: Op[], origin: Origin = "app"): Op[] {
    return this.confirmNow(ref, ops, false, origin);
  }

  private confirmNow(ref: DocRef, ops: Op[], edit: boolean, as?: Origin): Op[] {
    const doc = this.get(ref);
    if (!doc) {
      this.log.debug("a change to a document nobody holds was dropped", { record: ref.record });
      return [];
    }
    const applied = this.applyAll(doc, doc.confirmed, ops, edit);
    if (!applied.length) return applied;
    const from = doc.version;
    const origin: Origin = as ?? (edit ? "user" : "app");
    this.confirmed({ doc, ops: applied, origin });
    if (doc.layers.length) {
      // Open layers go on top again; readers may see more than these ops changed.
      if (this.recompute(doc)) this.notify({ doc, state: "confirmed", origin, from, ops: [], whole: true });
    } else {
      this.applyAll(doc, doc.value, applied, edit, true);
      doc.version += 1;
      this.notify({ doc, state: "confirmed", origin, from, ops: applied });
    }
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
    const from = doc.version;
    doc.version += 1;
    let touched = this.decisions.get(decision);
    if (!touched) this.decisions.set(decision, (touched = new Set()));
    touched.add(refKey(ref));
    this.notify({ doc, state: "tentative", origin: "app", from, ops: applied, decision });
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
      if (keep) {
        const folded = mine.flatMap((layer) => this.applyAll(doc, doc.confirmed, layer.ops, false, true));
        if (folded.length) this.confirmed({ doc, ops: folded, origin: "engine" });
      }
      const from = doc.version;
      // A decision whose layers were the only ones changes nothing readers see when it returns:
      // the confirmed value has caught up with the visible one, op by op.
      const changed = keep && doc.layers.length === 0 ? false : this.recompute(doc);
      this.notify({ doc, state: keep ? "confirmed" : "rolledback", origin: "engine", from, ops: [], decision, ...(changed ? { whole: true as const } : {}) });
    }
  }

  /** Every document's visible value, for tests: never logged. */
  snapshot(): Record<string, Json> {
    const out: Record<string, Json> = {};
    for (const [k, d] of this.docs) out[k] = stripKeys(d.value);
    return out;
  }
}
