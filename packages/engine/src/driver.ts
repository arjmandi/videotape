// The headless driver: plays journeys without a client, for tests (06 §8.1). It stands where a
// client will: it numbers its inputs and names the frame it saw, keeps secrets in a client-side
// buffer (as a platform's secure editor does) until the submit that sends them, clears them when
// the session says so, and records what it heard, including each document as it was at every
// change.
//
//   const s = await Headless.open(engine, { tape: "login" });
//   await s.fill({ username: "ada@example.com", password: "nope" });
//   await s.press("Sign in");
//   s.at("login"); s.error; s.secret("password"); s.doc("Credentials");

import type { Engine, OpenOptions } from "./engine";
import type { JsonObject } from "./intent";
import { type ReelView, labelText } from "./journey";
import type { DocRef, UserRecord } from "./protocol";
import { KEY, stripKeys } from "./records";
import type { Effect, FrameView, Input, Session, SessionEvent } from "./session";

export interface DocSeen {
  record: string;
  state: "confirmed" | "tentative" | "rolledback";
  /** Whether the document still carried changes of a running decision after this change. */
  tentative: boolean;
  /** The document as the session saw it right after the change (unless the driver keeps no snapshots). */
  value: any;
  /** When it was heard, in ms (performance.now()). */
  at: number;
}

/** Which item of a list an action is for: its index, its key, or the first item that matches. */
export type ItemChoice = number | string | ((item: any) => boolean);

type Body<T> = T extends unknown ? Omit<T, "seq" | "frame"> : never;

export class Headless {
  /** Everything the session said, in order. */
  events: SessionEvent[] = [];
  /** Each change to a document the frame showed, with the document as it was then. */
  changes: DocSeen[] = [];
  private seq = 0;
  private readonly secrets = new Map<string, string>();
  private readonly snapshots: boolean;

  /**
   * A driver for a session; `events` are what it heard before (its first frame), if it listened.
   * Without `snapshots`, changes are recorded without a copy of the document (for measurements).
   */
  constructor(readonly session: Session, events?: SessionEvent[], opts: { snapshots?: boolean } = {}) {
    this.snapshots = opts.snapshots ?? true;
    if (events) {
      this.events = events;
      session.on((e) => this.hear(e, false));
    } else {
      session.on((e) => this.hear(e, true));
    }
  }

  /** Opens a session on `engine` and drives it from its first frame. */
  static async open(engine: Engine, opts: OpenOptions = {}, driver: { snapshots?: boolean } = {}): Promise<Headless> {
    const events: SessionEvent[] = [];
    const session = await engine.open({ ...opts, listener: (e) => events.push(e) });
    return new Headless(session, events, driver);
  }

  private get engine(): Engine {
    return this.session["engine"] as Engine;
  }

  private hear(e: SessionEvent, record: boolean): void {
    if (record) this.events.push(e);
    if (e.t === "clear") for (const f of e.fields) this.secrets.delete(f);
    if (e.t === "doc") {
      const docs = this.engine.docs;
      const value = this.snapshots ? docs.read(e.ref) : undefined;
      this.changes.push({ record: e.record, state: e.state, tentative: docs.isTentative(e.ref), value, at: performance.now() });
    }
  }

  // ── reading ────────────────────────────────────────────────────────────────

  get view(): FrameView {
    return this.session.view();
  }

  /** The place on screen: `tape`, or `tape/id` in a tape of several. */
  get place(): string {
    return this.session.reel.place;
  }

  at(place: string): boolean {
    return this.place === place;
  }

  get reel(): ReelView {
    return this.session.reel.describe();
  }

  /** The frame's error status, as text (a message key's key for copy with parameters). */
  get error(): string | null {
    const e = this.session.status.error;
    return e === null ? null : labelText(e);
  }

  get invalid(): Record<string, string[]> {
    return { ...this.session.status.invalid };
  }

  get pending(): boolean {
    return this.session.status.pending;
  }

  get user(): UserRecord | null {
    return this.session.user;
  }

  private slot(name: string): DocRef | undefined {
    return this.session.ref(name);
  }

  /** A document the frame shows or edits, by record name (or `Item[]` for a shown list), as the user sees it. */
  doc(name: string): any {
    const ref = this.slot(name);
    return ref ? this.engine.docs.read(ref) : undefined;
  }

  /** Whether that document carries changes of a decision still running. */
  tentative(name: string): boolean {
    const ref = this.slot(name);
    return ref ? this.engine.docs.isTentative(ref) : false;
  }

  /** The changes heard to one document, by record name. */
  changesTo(record: string): DocSeen[] {
    return this.changes.filter((c) => c.record === record);
  }

  /** The items of a list field (`Inbox.items`, or `Deal[]` for a shown list), with their keys. */
  items(field: string): Array<{ key: string; value: any }> {
    const [slot, name] = field.endsWith("[]") ? [field, ""] : (field.split(".") as [string, string]);
    const ref = this.slot(slot);
    const doc = ref && this.engine.docs.get(ref);
    if (!doc) return [];
    const list = name ? (doc.value as JsonObject)[name] : doc.value;
    if (!Array.isArray(list)) return [];
    return list.map((item) => ({ key: String((item as JsonObject)[KEY]), value: stripKeys(item) }));
  }

  /** What the client's secure editor holds for a secret field (empty once the session cleared it). */
  secret(field: string): string {
    return this.secrets.get(this.qualify(field)) ?? "";
  }

  effects(): Effect[] {
    return this.events.flatMap((e) => (e.t === "effect" ? [e.effect] : []));
  }

  /** Why inputs were dropped, in order. */
  dropped(): string[] {
    return this.events.flatMap((e) => (e.t === "dropped" ? [e.reason] : []));
  }

  // ── acting ─────────────────────────────────────────────────────────────────

  /** Sends one input as a client would: numbered, and made against the frame on screen. */
  send(body: Body<Input>, frame = this.session.version): Promise<void> {
    return this.session.input({ ...body, seq: ++this.seq, frame } as Input);
  }

  private qualify(field: string): string {
    if (field.includes(".")) return field;
    const edit = this.session.frame.edit?.record;
    return edit ? `${edit}.${field}` : field;
  }

  /**
   * Types into fields of the edited record: `fill({ username: "ada" })`, or `fill("Draft.text", "hi")`.
   * A secret stays in the driver, as in a secure editor, until the submit that sends it.
   */
  async fill(values: Record<string, unknown> | string, value?: unknown): Promise<void> {
    const entries = typeof values === "string" ? [[values, value] as const] : Object.entries(values);
    const fields = this.view.fields;
    for (const [name, v] of entries) {
      const field = this.qualify(name);
      if (fields.find((f) => f.field === field)?.secret) {
        this.secrets.set(field, String(v));
        continue;
      }
      await this.send({ t: "fill", field, value: v });
    }
  }

  /**
   * Presses an action by its label (or id: `submit`, `action:<n>`, `select:<field>`). An action on
   * items needs `item`. The submit carries the secrets the driver holds for this frame.
   */
  async press(action: string, opts: { item?: ItemChoice; secrets?: Record<string, string> } = {}): Promise<void> {
    const view = this.view;
    const matches = view.actions.filter((a) => a.id === action || a.label === action);
    const found = matches.find((a) => a.id === action) ?? (matches.length > 1 ? matches.find((a) => a.kind === "submit") : matches[0]);
    const id = found?.id ?? action;
    const body: { t: "press"; action: string; item?: string; secrets?: Record<string, string> } = { t: "press", action: id };
    if (opts.item !== undefined) body.item = this.pick(id, opts.item);
    if (opts.secrets) body.secrets = opts.secrets;
    else if (found?.kind === "submit") {
      const held = view.fields.filter((f) => f.secret && this.secrets.has(f.field));
      if (held.length) body.secrets = Object.fromEntries(held.map((f) => [f.field, this.secrets.get(f.field)!]));
    }
    await this.send(body);
  }

  /** Selects an item of a list whose selection goes somewhere: `select("Inbox.items", 1)`. */
  select(field: string, item: ItemChoice): Promise<void> {
    return this.press(`select:${field}`, { item });
  }

  private pick(action: string, choice: ItemChoice): string {
    if (typeof choice === "string") return choice;
    const places = this.engine.places;
    const list = places.actions(this.session.frame).find((a) => a.id === action)?.list;
    if (!list) return String(choice);
    const items = this.items(list.field ? `${list.record}.${list.field}` : list.record);
    const found = typeof choice === "number" ? items[choice] : items.find((i) => choice(i.value));
    return found?.key ?? "?";
  }

  back(): Promise<void> {
    return this.send({ t: "back" });
  }

  /** Goes through a hub door, by the destination's tape or its label. */
  door(destination: string): Promise<void> {
    const hub = this.engine.intent.hub ?? [];
    const d = hub.find((x) => x.tape === destination || labelText(x.label) === destination);
    return this.send({ t: "hub", tape: d?.tape ?? destination });
  }

  /** The key of the item at `index` of a list field (`Inbox`, `items`), as the engine keyed it. */
  key(slot: string, field: string, index: number): string {
    return this.items(field ? `${slot}.${field}` : slot)[index]?.key ?? "?";
  }

  close(): void {
    this.engine.close(this.session);
  }
}
