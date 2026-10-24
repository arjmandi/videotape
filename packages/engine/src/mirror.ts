// The app's mirror (05 §6.2, Q53, Q57, Q68): the app process keeps a copy of the confirmed value of
// each document its handlers touch, and the engine keeps that copy current with `sync`. This is the
// engine's record of what the app holds, and at which confirmed version (`cversion`). A request
// names a document and that version, and carries its value only when the app does not hold it. Each
// decision works on its own copy of the confirmed value (Q68), so tentative changes never reach the
// mirror: a decision's changes reach it when they are confirmed. Records with secret fields are
// never mirrored: a decision gets them whole, secrets included, once.

import type { AppLink } from "./app-link";
import { type ConfirmedChange, type DocumentStore, refKey } from "./documents";
import type { Json } from "./intent";
import type { DocRef, DocValue, MirrorChange } from "./protocol";
import type { Records } from "./records";

export class AppMirror {
  /** The confirmed version of each document the app holds, by ref key. */
  private readonly held = new Map<string, number>();

  constructor(private readonly link: AppLink, private readonly docs: DocumentStore, private readonly records: Records) {}

  /** Whether the app may keep a copy: not a record with secret fields, and not a shown list. */
  mirrorable(record: string): boolean {
    return this.records.has(record) && this.records.secretFields(record).length === 0;
  }

  holds(ref: DocRef): number | undefined {
    return this.held.get(refKey(ref));
  }

  /**
   * How a request names a document: by ref and version when the app holds that version; whole, once,
   * when it does not (and from then on the app holds it). `extra` is merged into a value that is
   * sent: the secrets of the decision that carries it.
   */
  entry(ref: DocRef, extra?: Record<string, Json>): DocValue | undefined {
    const doc = this.docs.get(ref);
    if (!doc) return undefined;
    const key = refKey(ref);
    if (!this.mirrorable(doc.record)) {
      const c = doc.confirmed;
      const value = extra && typeof c === "object" && c !== null && !Array.isArray(c) ? { ...c, ...extra } : c;
      return { ref, version: doc.cversion, value };
    }
    if (this.held.get(key) === doc.cversion) return { ref, version: doc.cversion };
    this.held.set(key, doc.cversion);
    return { ref, version: doc.cversion, value: doc.confirmed };
  }

  /** The app said it does not hold these at the version asked for. */
  stale(refs: DocRef[]): void {
    for (const ref of refs) this.held.delete(refKey(ref));
  }

  forget(refs: DocRef[]): void {
    this.stale(refs);
  }

  private send(changes: MirrorChange[]): void {
    this.link.send({ t: "sync", changes });
  }

  private whole(ref: DocRef): MirrorChange | undefined {
    const doc = this.docs.get(ref);
    if (!doc) return undefined;
    this.held.set(refKey(ref), doc.cversion);
    return { doc: ref, version: doc.cversion, value: doc.confirmed };
  }

  /** Keeps the app's copy current with a confirmed change it did not make itself: a user's edit, a
   *  decision confirmed, a reload. The app's own changes outside decisions are echoed (`echo`). */
  confirmed(change: ConfirmedChange): void {
    if (change.origin === "app") return;
    const key = refKey(change.doc.ref);
    const have = this.held.get(key);
    if (have === undefined || have === change.doc.cversion) return;
    if (!change.whole && change.from === have && change.ops.length) {
      this.held.set(key, change.doc.cversion);
      this.send([{ doc: change.doc.ref, from: have, version: change.doc.cversion, ops: change.ops }]);
      return;
    }
    const w = this.whole(change.doc.ref);
    if (w) this.send([w]);
  }

  /**
   * After the app's own ops outside any decision on a document it holds (they went through its copy):
   * tells it the confirmed version they reached, so it moves its copy along without applying them
   * again; if the engine refused any of them, the copy is wrong, so it gets the value whole.
   */
  echo(ref: DocRef, from: number | undefined, complete: boolean): void {
    const key = refKey(ref);
    const have = this.held.get(key);
    const doc = this.docs.get(ref);
    if (have === undefined || !doc) return;
    if (complete && from === have && doc.cversion !== have) {
      this.held.set(key, doc.cversion);
      this.send([{ doc: ref, from: have, version: doc.cversion, origin: "app" }]);
      return;
    }
    const w = this.whole(ref);
    if (w) this.send([w]);
  }

  /** The document is gone from the engine: the app drops its copy too. */
  dropped(ref: DocRef): void {
    if (this.held.delete(refKey(ref))) this.link.send({ t: "sync", drop: [ref] });
  }

  /** Documents the app asked for: those the engine holds, whole; it holds them from now on. */
  fetched(id: string, refs: DocRef[]): void {
    const documents: Array<{ doc: DocRef; version: number; value: Json }> = [];
    for (const ref of refs) {
      const doc = this.docs.get(ref);
      if (!doc || !this.mirrorable(doc.record)) continue;
      this.held.set(refKey(ref), doc.cversion);
      documents.push({ doc: ref, version: doc.cversion, value: doc.confirmed });
    }
    this.link.send({ t: "fetched", id, documents });
  }
}
