// A session: one user on one device, walking a reel (05 §6.3, §11). Inputs arrive as messages,
// validated against the frame they were made against, with sequence guards carried over from
// prototype-0's VTP: a replayed `seq` or an input for a frame that is no longer current is dropped.
// What the document can answer (a fill) the engine answers at once; a press that needs a decision
// calls the app's handler and plays the outcome it returns.

import { z } from "zod";
import { AppUnavailable } from "./app-link";
import type { DocState } from "./documents";
import type { Engine } from "./engine";
import type { Declared, Frame, Json, JsonObject, Label, Outcome, Target } from "./intent";
import { type FrameAction, type FrameField, Reel, type ReelState, type ReelView, type Step, type Visit, labelText } from "./journey";
import { scrub } from "./log";
import type { DecideRequest, DocRef, DocValue, Loaded, Op, ResultMessage, UserRecord } from "./protocol";
import { KEY, type PathSegment, stripKeys } from "./records";

export const SOMETHING_WENT_WRONG = "Something went wrong. Please try again.";
export const APP_UNAVAILABLE = "The app is not available right now. Please try again.";
/** Largest value, as JSON, one fill may carry. */
export const MAX_VALUE_CHARS = 65_536;

// ── inputs ───────────────────────────────────────────────────────────────────

const seq = z.number().int().positive();
/** The frame version an input was made against; the scene version takes its place with scene state. */
const frame = z.number().int().nonnegative();

export const InputSchema = z.discriminatedUnion("t", [
  z.object({ t: z.literal("fill"), seq, frame, field: z.string().min(1).max(256), value: z.unknown() }).strict(),
  z.object({
    t: z.literal("press"), seq, frame,
    action: z.string().min(1).max(256),
    item: z.string().min(1).max(1024).optional(),
    secrets: z.record(z.string().max(256), z.string().max(4096)).optional(),
  }).strict(),
  z.object({ t: z.literal("back"), seq, frame }).strict(),
  z.object({ t: z.literal("hub"), seq, frame, tape: z.string().min(1).max(256) }).strict(),
]);
export type Input = z.infer<typeof InputSchema>;

// ── what a session tells its client ──────────────────────────────────────────

export interface Status {
  /** A decision is in flight: the world plays "handler pending" (05 §9.1). */
  pending: boolean;
  /** The frame's error status: a `Reject`'s message, or the engine's when the app failed. */
  error: Label | null;
  /** Validation problems by field, which the engine finds without the app. */
  invalid: Record<string, string[]>;
}

export interface FrameView {
  version: number;
  place: string;
  tape: string;
  frame: string | null;
  purpose: string;
  title?: Label;
  reel: ReelView;
  actions: Array<{ id: string; label: string; kind: FrameAction["kind"]; on?: string; role?: string }>;
  fields: FrameField[];
  documents: Record<string, DocRef>;
  /** The slots whose documents carry changes of decisions still running. */
  tentative: string[];
  status: Status;
}

export type Effect =
  | { type: "open"; url: Json }
  | { type: "download"; name: string; data: string; encoding?: "base64" }
  | { type: "copy"; value: Json };

export type SessionEvent =
  | { t: "frame"; view: FrameView }
  | { t: "doc"; ref: DocRef; record: string; state: DocState; version: number; decision?: string }
  | { t: "status"; status: Status }
  | { t: "clear"; fields: string[] }
  | { t: "effect"; effect: Effect }
  | { t: "dropped"; seq: number; reason: string };

export type Listener = (e: SessionEvent) => void;

const isObject = (v: unknown): v is JsonObject => typeof v === "object" && v !== null && !Array.isArray(v);

export class Session {
  readonly reel: Reel;
  user: UserRecord | null;
  version = 0;
  status: Status = { pending: false, error: null, invalid: {} };
  closed = false;
  detachedAt: number | undefined;
  private inSeq = 0;
  private readonly listeners = new Set<Listener>();
  private queue: Promise<void> = Promise.resolve();
  private readonly held = new Set<Visit>();
  /** The step on screen: inputs are read against it while a move waits for its frame's loader. */
  private shown!: Step;

  /** When the session last moved or took an input: the most recent journey is the one a new device resumes. */
  lastActive = Date.now();

  constructor(private readonly engine: Engine, readonly id: string, readonly token: string, user: UserRecord | null, readonly device: string) {
    this.reel = new Reel(engine.places);
    this.user = user;
  }

  private get log() {
    return this.engine.log;
  }

  private get docs() {
    return this.engine.docs;
  }

  // ── listening ──────────────────────────────────────────────────────────────

  on(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  emit(e: SessionEvent): void {
    for (const l of this.listeners) l(e);
  }

  private statusChanged(): void {
    this.emit({ t: "status", status: this.copyStatus() });
  }

  private copyStatus(): Status {
    return { pending: this.status.pending, error: this.status.error, invalid: { ...this.status.invalid } };
  }

  // ── starting ───────────────────────────────────────────────────────────────

  /** Starts the journey: at the entry, at a tape, at the frame an address opens, or (`resume`) where
   *  `resumeFrom` put the reel. */
  async begin(opts: { address?: string; tape?: string; args?: JsonObject; resume?: boolean }): Promise<void> {
    const places = this.engine.places;
    if (opts.resume) {
      // the reel holds a journey taken over from another session
    } else if (opts.address !== undefined) {
      const m = places.matchAddress(opts.address);
      if (!m) throw new Error(`no frame has the address ${opts.address}`);
      this.reel.open(m.tape, m.frame, m.args);
    } else {
      const tape = opts.tape ?? this.engine.intent.entry;
      if (!places.hasTape(tape)) throw new Error(`no tape ${tape}`);
      this.reel.start(tape, opts.args ?? {});
    }
    await this.arrive();
  }

  /**
   * Takes over another session's journey (05 §6.2, Q62): where it is, its history, its calls, and
   * its saved hub histories. Shared documents are held again; a session's own (a draft) are copied.
   */
  resumeFrom(src: Session): void {
    const visits = new Map<Visit, Visit>();
    const sameDevice = src.device === this.device;
    this.reel.copy(src.reel, (v) => {
      const known = visits.get(v);
      if (known) return known;
      const copy = this.reel.visit(v.tape, structuredClone(v.args));
      const holder = this.holder(copy);
      for (const [slot, ref] of v.docs) {
        const doc = this.docs.get(ref);
        if (!doc) continue;
        if ("id" in ref) {
          this.docs.hold(ref, holder);
          copy.docs.set(slot, ref);
        } else {
          copy.docs.set(slot, this.docs.own(doc.record, structuredClone(doc.value), holder));
        }
      }
      this.held.add(copy);
      visits.set(v, copy);
      return copy;
    });
    // An earlier session on this device ends: this one is its user's journey here now.
    if (sameDevice) this.engine.close(src);
  }

  // ── reading ────────────────────────────────────────────────────────────────

  /** The frame on screen: the reel's step once its frame was entered (a move waits for its loader). */
  get frame(): Frame {
    return this.engine.places.frame(this.shown.visit.tape, this.shown.frame);
  }

  /** The document a slot of the frame on screen holds: a record name, or `Item[]` for a shown list. */
  ref(slot: string): DocRef | undefined {
    return this.shown.visit.docs.get(slot);
  }

  /** Whether the frame on screen shows (or edits) this document. */
  shows(ref: DocRef): boolean {
    const key = JSON.stringify(ref);
    const visit = this.shown.visit;
    return this.engine.places.slots(this.frame).some((s) => {
      const held = visit.docs.get(s.slot);
      return held !== undefined && JSON.stringify(held) === key;
    });
  }

  view(): FrameView {
    const frame = this.frame;
    const places = this.engine.places;
    const visit = this.shown.visit;
    const documents: Record<string, DocRef> = {};
    for (const s of places.slots(frame)) {
      const ref = visit.docs.get(s.slot);
      if (ref) documents[s.slot] = ref;
    }
    return {
      version: this.version,
      place: this.reel.place,
      tape: visit.tape,
      frame: frame.id ?? null,
      purpose: frame.purpose,
      ...(frame.title !== undefined ? { title: frame.title } : {}),
      reel: this.reel.describe(),
      actions: places.actions(frame).map((a) => ({
        id: a.id, label: labelText(a.label), kind: a.kind,
        ...(a.list ? { on: a.list.item } : {}), ...(a.role ? { role: a.role } : {}),
      })),
      fields: places.fields(frame),
      documents,
      tentative: Object.entries(documents).filter(([, ref]) => this.docs.isTentative(ref)).map(([slot]) => slot),
      status: this.copyStatus(),
    };
  }

  // ── inputs ─────────────────────────────────────────────────────────────────

  /**
   * Takes one input. Fills are answered at once; presses, back, and the hub's doors are handled one
   * at a time, in order. Resolves when the input (and everything queued before it) is handled.
   */
  input(raw: unknown): Promise<void> {
    if (this.closed) return Promise.resolve();
    const parsed = InputSchema.safeParse(raw);
    if (!parsed.success) {
      const s = isObject(raw) && typeof raw.seq === "number" ? raw.seq : 0;
      this.drop(s, "malformed input");
      return this.queue;
    }
    const msg = parsed.data;
    if (msg.seq <= this.inSeq) {
      this.drop(msg.seq, "replayed seq");
      return this.queue;
    }
    this.inSeq = msg.seq;
    if (msg.t === "fill") {
      this.fill(msg);
      return this.queue;
    }
    const run = () => this.handle(msg);
    this.queue = this.queue.then(run).catch((e: unknown) => {
      this.log.error("an input failed", { session: this.id, t: msg.t, error: e instanceof Error ? e.message : String(e) });
      this.status.pending = false;
      this.status.error = SOMETHING_WENT_WRONG;
      this.statusChanged();
    });
    return this.queue;
  }

  private drop(seq: number, reason: string): void {
    this.log.warn(`dropped an input: ${reason}`, { session: this.id, seq });
    this.emit({ t: "dropped", seq, reason });
  }

  private stale(msg: { seq: number; frame: number }): boolean {
    if (msg.frame === this.version) return false;
    this.drop(msg.seq, "stale frame");
    return true;
  }

  private async handle(msg: Exclude<Input, { t: "fill" }>): Promise<void> {
    if (this.stale(msg)) return;
    switch (msg.t) {
      case "press":
        return this.press(msg);
      case "back": {
        if (!this.reel.canGoBack) return this.drop(msg.seq, "no history here");
        const undo = this.undoable();
        this.reel.back();
        return this.arrive(undo);
      }
      case "hub": {
        if (!this.reel.showsHub) return this.drop(msg.seq, "this frame shows no hub");
        if (!this.engine.places.isDestination(msg.tape)) return this.drop(msg.seq, "not a hub destination");
        const undo = this.undoable();
        this.reel.door(msg.tape);
        return this.arrive(undo);
      }
    }
  }

  /** A user's edit of a field of the record the frame edits: a local change, no app involved. */
  private fill(msg: Extract<Input, { t: "fill" }>): void {
    if (this.stale(msg)) return;
    const field = this.engine.places.fields(this.frame).find((f) => f.field === msg.field);
    if (!field) return this.drop(msg.seq, "not a field this frame edits");
    if (field.secret) return this.drop(msg.seq, "secrets travel with the press that submits them");
    if (msg.value === undefined || JSON.stringify(msg.value).length > MAX_VALUE_CHARS) return this.drop(msg.seq, "invalid value");
    const records = this.engine.records;
    if (!records.fits(field.record, field.name, msg.value)) return this.drop(msg.seq, "invalid value");
    const ref = this.ref(field.record);
    if (!ref) return this.drop(msg.seq, "the frame has no document to edit");
    const value = msg.value as Json;
    const problems = records.validateField(field.record, field.name, value);
    this.docs.edit(ref, [{ op: "set", path: [field.name], value }]);
    const before = JSON.stringify(this.status.invalid[field.field] ?? []);
    if (problems.length) this.status.invalid[field.field] = problems;
    else delete this.status.invalid[field.field];
    if (before !== JSON.stringify(this.status.invalid[field.field] ?? [])) this.statusChanged();
  }

  private async press(msg: Extract<Input, { t: "press" }>): Promise<void> {
    const action = this.engine.places.actions(this.frame).find((a) => a.id === msg.action);
    if (!action) return this.drop(msg.seq, "not an action on this frame");
    let item: Item | undefined;
    if (action.list) {
      if (msg.item === undefined) return this.drop(msg.seq, "an action on items needs an item");
      item = this.item(action.list, msg.item);
      if (!item) return this.drop(msg.seq, "no such item");
    } else if (msg.item !== undefined) {
      return this.drop(msg.seq, "this action is not on items");
    }
    const secretFields = this.engine.places.fields(this.frame).filter((f) => f.secret);
    const secrets: Record<string, string> = {};
    for (const [name, value] of Object.entries(msg.secrets ?? {})) {
      const f = secretFields.find((s) => s.field === name || s.name === name);
      if (!f) return this.drop(msg.seq, "secrets name a field that is not a secret of this frame");
      secrets[f.name] = value;
    }
    try {
      await this.act(action, item, secrets);
    } finally {
      if (secretFields.length && Object.keys(secrets).length) {
        // A secret reaches the handler once (05 §6.1): whatever happened, the client clears its editor.
        this.emit({ t: "clear", fields: secretFields.map((f) => f.field) });
      }
    }
  }

  /** The item of a list a press names by key, and where it is. */
  private item(list: NonNullable<FrameAction["list"]>, key: string): Item | undefined {
    const ref = this.ref(list.record);
    const doc = ref && this.docs.get(ref);
    if (!ref || !doc) return undefined;
    const items = list.field === "" ? doc.value : isObject(doc.value) ? doc.value[list.field] : undefined;
    if (!Array.isArray(items)) return undefined;
    const value = items.find((i) => isObject(i) && i[KEY] === key);
    if (value === undefined) return undefined;
    return { ref, record: list.item, path: list.field === "" ? [{ key }] : [list.field, { key }], value };
  }

  private async act(action: FrameAction, item: Item | undefined, secrets: Record<string, string>): Promise<void> {
    const target = action.target;
    if ("handler" in target) {
      if (action.kind === "submit" && !this.valid(secrets)) return;
      return this.decide(target.handler, { item, secrets });
    }
    return this.play(this.resolve(target, item), { item });
  }

  /** Validates the edited document, with the secrets the press carries, before a submit reaches the app. */
  private valid(secrets: Record<string, string>): boolean {
    const edit = this.frame.edit?.record;
    const ref = edit ? this.ref(edit) : undefined;
    if (!edit || !ref) return true;
    const value = { ...(this.docs.read(ref) as JsonObject), ...secrets };
    const invalid: Record<string, string[]> = {};
    for (const problem of this.engine.records.validate(edit, value)) {
      const missing = /^\/ must have required property '(.+)'$/.exec(problem);
      const field = missing ? missing[1]! : problem.split(" ")[0]!.split("/")[1] ?? "";
      const key = field ? `${edit}.${field}` : edit;
      (invalid[key] ??= []).push(missing ? "is required" : problem.slice(problem.indexOf(" ") + 1));
    }
    this.status.invalid = invalid;
    if (Object.keys(invalid).length === 0) return true;
    this.status.error = null;
    this.statusChanged();
    return false;
  }

  /** An outcome written in intent, with its field references filled from the item or the frame's documents. */
  private resolve(target: Outcome, item: Item | undefined): Outcome {
    const fill = (v: Json): Json => {
      if (isObject(v) && typeof v.field === "string" && Object.keys(v).length === 1) return this.fieldValue(v.field, item) ?? null;
      return v;
    };
    if ((target.type === "jump" || target.type === "call") && target.args) {
      return { ...target, args: Object.fromEntries(Object.entries(target.args).map(([k, v]) => [k, fill(v)])) };
    }
    if (target.type === "done" && isObject(target.result) && typeof target.result.item === "string") {
      return { type: "done", result: item ? stripKeys(item.value) : null };
    }
    if (target.type === "copy") return target;
    return target;
  }

  /** `Record.field` (or a chain) read from the item when it is that record, else from the frame's document. */
  private fieldValue(ref: string, item: Item | undefined): Json | undefined {
    const [record, ...path] = ref.split(".");
    let value: Json | undefined;
    if (item && item.record === record) value = item.value;
    else {
      const doc = record ? this.ref(record) : undefined;
      value = doc ? (this.docs.read(doc) as Json) : undefined;
    }
    for (const p of path) value = isObject(value) ? value[p] : undefined;
    return value === undefined ? undefined : stripKeys(value);
  }

  // ── decisions ──────────────────────────────────────────────────────────────

  /** Calls a handler over the app protocol and plays its outcome; a Reject or a failure stays. */
  private async decide(handler: string, opts: { item?: Item | undefined; secrets?: Record<string, string>; values?: JsonObject }): Promise<void> {
    const engine = this.engine;
    const link = engine.link;
    const spec = engine.intent.handlers[handler];
    if (!spec) throw new Error(`no handler ${handler}`);
    if (!link) {
      this.status.error = APP_UNAVAILABLE;
      this.statusChanged();
      return;
    }
    const secrets = opts.secrets ?? {};
    const values: JsonObject = { ...(opts.values ?? {}) };
    const edit = this.frame.edit?.record;
    /** The documents by reference and version (Q57); whole only where the app does not hold them. */
    const documents = (): Record<string, DocValue> => {
      const out: Record<string, DocValue> = {};
      const mirror = engine.mirror;
      for (const p of spec.params) {
        if (p.name in values || p.type !== "record" || !p.record || !mirror) continue;
        if (opts.item && opts.item.record === p.record) {
          const entry = mirror.entry(opts.item.ref);
          if (entry) out[p.name] = { ...entry, path: opts.item.path, record: p.record };
          continue;
        }
        const ref = this.ref(p.record);
        const entry = ref && mirror.entry(ref, p.record === edit ? secrets : undefined);
        if (entry) out[p.name] = entry;
      }
      return out;
    };

    this.status.pending = true;
    this.status.error = null;
    this.statusChanged();
    let decision: string | undefined;
    let result: ResultMessage | undefined;
    try {
      for (let attempt = 0; ; attempt++) {
        const request: Omit<DecideRequest, "id" | "t"> = { handler, session: this.id, user: this.user, documents: documents() };
        if (Object.keys(values).length) request.values = values;
        result = await link.decide(request, Object.values(secrets), (id) => (decision = id));
        // The app's copy was missing or behind: send those documents whole, once, and ask again.
        if (!("stale" in result) || attempt > 0) break;
        engine.mirror?.stale(result.stale.map((s) => s.doc));
      }
    } catch (e) {
      if (decision) this.docs.rollback(decision);
      this.status.pending = false;
      this.status.error = e instanceof AppUnavailable ? APP_UNAVAILABLE : SOMETHING_WENT_WRONG;
      this.log.warn("a decision failed", { session: this.id, handler, reason: e instanceof AppUnavailable ? e.code : String(e) });
      this.statusChanged();
      return;
    }
    this.status.pending = false;
    if ("outcome" in result) {
      const outcome = result.outcome as unknown as Outcome;
      if (!declares(spec.outcomes, outcome) || !this.playable(outcome)) {
        this.docs.rollback(decision!);
        this.log.error("a handler returned an outcome its intent does not declare", { session: this.id, handler, type: outcome.type });
        this.status.error = SOMETHING_WENT_WRONG;
        this.statusChanged();
        return;
      }
      this.docs.confirm(decision!);
      this.statusChanged();
      return this.play(outcome, { item: opts.item });
    }
    this.docs.rollback(decision!);
    if ("reject" in result) {
      this.status.error = result.reject.message;
    } else if ("stale" in result) {
      this.log.error("the app's copy of a document stayed stale", { session: this.id, handler });
      this.status.error = SOMETHING_WENT_WRONG;
    } else {
      const error = "error" in result ? result.error : { type: "BadResult", message: "" };
      this.log.error("a handler raised", { session: this.id, handler, type: error.type, message: scrub(error.message, Object.values(secrets)).slice(0, 500) });
      this.status.error = SOMETHING_WENT_WRONG;
    }
    this.statusChanged();
  }

  /** Whether an outcome names places that exist; a handler's outcome is checked before it plays. */
  private playable(o: Outcome): boolean {
    const places = this.engine.places;
    if (o.type === "jump" || o.type === "call") return places.hasTape(o.tape) && (o.type !== "call" || !o.then || o.then.handler in this.engine.intent.handlers);
    if (o.type === "goto") return places.frameIndex(this.reel.head.visit.tape, o.frame) >= 0;
    if ("sign_in" in o && o.sign_in !== undefined) return isUserRecord(o.sign_in);
    return true;
  }

  // ── outcomes ───────────────────────────────────────────────────────────────

  /** Plays an outcome: moves the reel, changes who is signed in, or hands the client an effect. */
  private async play(o: Outcome, ctx: { item?: Item | undefined }): Promise<void> {
    const identity = "sign_in" in o && o.sign_in !== undefined ? "in" : "sign_out" in o && o.sign_out ? "out" : undefined;
    const undo = this.undoable();
    if (identity === "out" && this.user) this.engine.signedOut(this);
    if (identity === "out") this.user = null;
    if (identity === "in") {
      this.user = (o as unknown as { sign_in: UserRecord }).sign_in;
      // Reels are keyed by user and device: a journey this user has elsewhere resumes here (Q62),
      // unless the outcome says resume=False (Q70).
      const from = this.engine.signedIn(this);
      if (from && (o as { resume?: boolean }).resume !== false) {
        this.resumeFrom(from);
        return this.arrive(undo);
      }
    }
    const reel = this.reel;
    switch (o.type) {
      case "stay":
        if (!identity) return;
        reel.reset();
        break;
      case "jump":
        if (identity) reel.start(o.tape, o.args ?? {});
        else reel.jump(o.tape, o.args ?? {});
        break;
      case "goto": {
        reel.goto(this.engine.places.frameIndex(reel.head.visit.tape, o.frame));
        if (identity) reel.reset();
        break;
      }
      case "back":
        if (reel.back() === "none" && !identity) return;
        if (identity) reel.reset();
        break;
      case "call":
        reel.call(o.tape, o.args ?? {}, o.then?.handler);
        break;
      case "done": {
        const returned = reel.done();
        if (!returned) {
          this.log.warn("done outside a call", { session: this.id });
          return;
        }
        await this.arrive(undo);
        if (returned.then) await this.decide(returned.then, { values: { result: (o.result ?? null) as Json } });
        return;
      }
      case "open":
        this.emit({ t: "effect", effect: { type: "open", url: o.url } });
        return;
      case "download":
        this.emit({ t: "effect", effect: { type: "download", name: o.name, data: o.data, ...(o.encoding ? { encoding: o.encoding } : {}) } });
        return;
      case "copy": {
        const value = o.field !== undefined ? this.fieldValue(o.field, ctx.item) : o.text;
        this.emit({ t: "effect", effect: { type: "copy", value: value ?? null } });
        return;
      }
    }
    await this.arrive(undo);
  }

  /** What a move undoes if the frame it goes to cannot be entered: where the reel was, and who was signed in. */
  private undoable(): Undo {
    return { reel: this.reel.save(), user: this.user };
  }

  /**
   * The head changed: enters its frame (runs its loader) and then shows it. If the loader fails on the
   * way (`undo` given), the move does not happen: the reel goes back to where it was and the error
   * shows on the frame the user is on (Q65). Only an entry or an address, with nowhere to stay,
   * enters the frame with its defaults and the error.
   */
  private async arrive(undo?: Undo): Promise<void> {
    this.lastActive = Date.now();
    const step = this.reel.head;
    let error: Label | null = null;
    if (!step.entered) {
      const entered = await this.enter(step, undo === undefined);
      if (this.closed) return;
      if (!entered.ok && undo) {
        this.reel.restore(undo.reel);
        this.user = undo.user;
        this.release();
        this.status.error = entered.error;
        this.statusChanged();
        return;
      }
      step.entered = true;
      error = entered.error;
    }
    this.version += 1;
    this.shown = step;
    this.release();
    this.status.error = error;
    this.status.invalid = {};
    this.emit({ t: "frame", view: this.view() });
  }

  private holder(visit: Visit): string {
    return `${this.id}:${visit.n}`;
  }

  private release(): void {
    const live = this.reel.live();
    for (const visit of this.held) {
      if (!live.has(visit)) {
        this.docs.release(this.holder(visit));
        this.held.delete(visit);
      }
    }
  }

  /**
   * Enters a frame: runs its loader, holds what it returns, and starts the rest from their defaults.
   * When the loader fails, it stops there, unless `anyway` (an entry, an address), where the frame
   * starts from its defaults and carries the error.
   */
  private async enter(step: Step, anyway: boolean): Promise<{ ok: boolean; error: Label | null }> {
    const engine = this.engine;
    const frame = engine.places.frame(step.visit.tape, step.frame);
    const visit = step.visit;
    const holder = this.holder(visit);
    this.held.add(visit);
    const slots = engine.places.slots(frame);
    let error: Label | null = null;
    if (frame.enter) {
      const result = await this.load(frame.enter.loader, visit);
      if (!result.ok) {
        error = result.error;
        if (!anyway) return { ok: false, error };
      }
      for (const d of result.documents) {
        const slot = "record" in d ? d.record : `${d.collection}[]`;
        const wanted = slots.find((s) => s.slot === slot);
        if (!wanted) {
          this.log.warn("a loader returned a document its frame does not show or edit", { session: this.id, loader: frame.enter.loader, record: slot });
          continue;
        }
        const ref = wanted.list ? this.docs.own(slot, d.value as Json, holder) : this.docs.load(wanted.record, d.value as Json, holder, wanted.edit);
        const old = visit.docs.get(slot);
        if (old && JSON.stringify(old) !== JSON.stringify(ref)) this.docs.drop(old, holder);
        visit.docs.set(slot, ref);
      }
    }
    for (const s of slots) {
      if (visit.docs.has(s.slot)) continue;
      const value: Json = s.list ? [] : engine.records.defaults(s.record);
      visit.docs.set(s.slot, this.docs.own(s.list ? s.slot : s.record, value, holder));
    }
    return { ok: error === null, error };
  }

  /** Runs a loader over the app protocol; a failure is the engine's own message, never the app's text. */
  private async load(loader: string, visit: Visit): Promise<{ ok: true; documents: Loaded[] } | { ok: false; error: Label; documents: [] }> {
    const engine = this.engine;
    const link = engine.link;
    const spec = engine.intent.loaders[loader];
    if (!link || !spec) return { ok: false, error: APP_UNAVAILABLE, documents: [] };
    const documents = (): Record<string, DocValue> => {
      const out: Record<string, DocValue> = {};
      for (const p of spec.params) {
        if (p.type !== "record" || !p.record) continue;
        const ref = visit.docs.get(p.record);
        const entry = ref && engine.mirror?.entry(ref);
        if (entry) out[p.name] = entry;
      }
      return out;
    };
    try {
      let result = await link.load({ loader, session: this.id, user: this.user, args: visit.args, documents: documents() });
      if ("stale" in result) {
        engine.mirror?.stale(result.stale.map((s) => s.doc));
        result = await link.load({ loader, session: this.id, user: this.user, args: visit.args, documents: documents() });
      }
      if ("documents" in result) return { ok: true, documents: result.documents };
      const error = "error" in result ? result.error : { type: "BadResult", message: "" };
      this.log.error("a loader raised", { session: this.id, loader, type: error.type, message: error.message.slice(0, 500) });
    } catch (e) {
      this.log.warn("a loader failed", { session: this.id, loader, reason: e instanceof AppUnavailable ? e.code : String(e) });
      return { ok: false, error: e instanceof AppUnavailable ? APP_UNAVAILABLE : SOMETHING_WENT_WRONG, documents: [] };
    }
    return { ok: false, error: SOMETHING_WENT_WRONG, documents: [] };
  }

  /** Ends the session: its documents are let go. */
  close(): void {
    if (this.closed) return;
    this.closed = true;
    for (const visit of this.held) this.docs.release(this.holder(visit));
    this.held.clear();
    this.listeners.clear();
  }
}

interface Undo {
  reel: ReelState;
  user: UserRecord | null;
}

interface Item {
  ref: DocRef;
  record: string;
  path: PathSegment[];
  value: Json;
}

function isUserRecord(v: unknown): v is UserRecord {
  return isObject(v) && typeof v.record === "string" && typeof v.id === "string" && isObject(v.value);
}

/** Whether a handler's declared outcomes (its intent) allow the one it returned. `stay` always is. */
export function declares(declared: Declared[], o: Outcome): boolean {
  if (o.type === "stay" && !("sign_in" in o && o.sign_in !== undefined) && !("sign_out" in o && o.sign_out)) return true;
  return declared.some((d) => {
    if (d.type !== o.type) return false;
    if (d.tape !== undefined && "tape" in o && d.tape !== o.tape) return false;
    if (d.frame !== undefined && "frame" in o && d.frame !== o.frame) return false;
    return true;
  });
}

export type { Op, Target };
