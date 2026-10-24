// The journey (05 §6.3): what the intent says about places, and the reel that walks them.
//
// A reel is a session's journey: the step it is on (a frame of a tape visit), the history back to
// its root, the calls it is inside, and, in an app with a hub, the saved history of each
// destination. A tape visit carries the tape's arguments and the documents its frames share, so a
// `goto` carries nothing and a wizard's steps share one draft (Q46).

import type { Action, Component, Frame, Intent, Json, JsonObject, Label, Tape, Target } from "./intent";
import { placeName } from "./intent";
import type { KeptJourney, KeptStep } from "./journeys";
import type { DocRef } from "./protocol";
import type { Records } from "./records";

// ── the intent, indexed ──────────────────────────────────────────────────────

/** Something a user can press on a frame. */
export interface FrameAction {
  id: string;
  label: Label;
  target: Target;
  kind: "submit" | "action" | "select" | "press";
  /** For actions on items and selects: the list whose items they act on. */
  list?: { record: string; field: string; item: string };
  role?: string;
}

/** A field a user can write on a frame: a field of the record it edits. */
export interface FrameField {
  field: string;
  record: string;
  name: string;
  type: string;
  secret: boolean;
}

interface Address {
  tape: string;
  frame: number;
  pattern: RegExp;
  params: string[];
}

export class Places {
  private readonly tapes = new Map<string, Tape>();
  private readonly addresses: Address[] = [];
  private readonly actionsCache = new Map<Frame, FrameAction[]>();
  readonly destinations: string[];

  constructor(readonly intent: Intent, private readonly records: Records) {
    for (const t of intent.tapes) {
      this.tapes.set(t.id, t);
      t.frames.forEach((f, i) => {
        if (f.address) this.addresses.push({ tape: t.id, frame: i, ...compileAddress(f.address) });
      });
    }
    this.destinations = (intent.hub ?? []).map((d) => d.tape);
  }

  tape(id: string): Tape {
    const t = this.tapes.get(id);
    if (!t) throw new Error(`no tape ${id}`);
    return t;
  }

  hasTape(id: string): boolean {
    return this.tapes.has(id);
  }

  frame(tape: string, index: number): Frame {
    const f = this.tape(tape).frames[index];
    if (!f) throw new Error(`no frame ${index} in ${tape}`);
    return f;
  }

  frameIndex(tape: string, id: string): number {
    return this.tape(tape).frames.findIndex((f) => f.id === id);
  }

  place(tape: string, index: number): string {
    return placeName(this.tape(tape), this.frame(tape, index));
  }

  isDestination(tape: string): boolean {
    return this.destinations.includes(tape);
  }

  /** The frame an address opens, and the tape arguments its parts supply. */
  matchAddress(path: string): { tape: string; frame: number; args: JsonObject } | undefined {
    for (const a of this.addresses) {
      const m = a.pattern.exec(path);
      if (!m) continue;
      const args: JsonObject = {};
      a.params.forEach((p, i) => (args[p] = decodeURIComponent(m[i + 1] ?? "")));
      return { tape: a.tape, frame: a.frame, args };
    }
    return undefined;
  }

  /** The documents a frame has: the records it shows and the one it edits, by slot. */
  slots(frame: Frame): Array<{ slot: string; record: string; edit: boolean; list: boolean }> {
    const out: Array<{ slot: string; record: string; edit: boolean; list: boolean }> = [];
    for (const s of frame.shows ?? []) {
      if (s.record) out.push({ slot: s.record, record: s.record, edit: false, list: false });
      else if (s.collection) out.push({ slot: `${s.collection}[]`, record: s.collection, edit: false, list: true });
    }
    if (frame.edit) out.push({ slot: frame.edit.record, record: frame.edit.record, edit: true, list: false });
    return out;
  }

  /** What can be pressed on a frame, with stable ids: `submit`, `action:<n>`, `select:<field>`, `press:<field>`. */
  actions(frame: Frame): FrameAction[] {
    const known = this.actionsCache.get(frame);
    if (known) return known;
    const out: FrameAction[] = [];
    if (frame.submit) out.push({ id: "submit", label: frame.submit.label, target: { handler: frame.submit.handler }, kind: "submit", role: "primary" });
    (frame.actions ?? []).forEach((a: Action, i) => {
      const list = a.on !== undefined ? this.listOf(frame, a.on) : undefined;
      out.push({ id: `action:${i}`, label: a.label, target: a.target, kind: "action", ...(list ? { list } : {}), ...(a.role ? { role: a.role } : {}) });
    });
    const walk = (components: Component[]) => {
      for (const c of components) {
        if (c.field && c.select) {
          const [record, field] = c.field.split(".") as [string, string];
          const item = c.item?.record;
          out.push({ id: `select:${c.field}`, label: c.field, target: c.select, kind: "select", ...(item ? { list: { record, field, item } } : {}) });
        }
        if (c.field && c.press) out.push({ id: `press:${c.field}`, label: (c.label as Label | undefined) ?? c.field, target: c.press, kind: "press" });
      }
    };
    walk(frame.components);
    this.actionsCache.set(frame, out);
    return out;
  }

  /** The list of a frame's documents whose items an `on=` names: a record (held once) or a field. */
  private listOf(frame: Frame, on: string | { field: string }): FrameAction["list"] {
    if (typeof on === "object") {
      const [record, field] = on.field.split(".") as [string, string];
      const item = this.records.kind(record, field)?.item?.record;
      return item ? { record, field, item } : undefined;
    }
    for (const s of this.slots(frame)) {
      if (s.list) {
        if (s.record === on) return { record: s.slot, field: "", item: on };
        continue;
      }
      for (const field of this.records.fields(s.record)) {
        const kind = this.records.kind(s.record, field);
        if (kind?.type === "collection" && kind.item?.record === on) return { record: s.record, field, item: on };
      }
    }
    return undefined;
  }

  /** The fields a user writes on a frame: those of the record it edits, as its components derive them. */
  fields(frame: Frame): FrameField[] {
    if (!frame.edit) return [];
    const record = frame.edit.record;
    return frame.components
      .filter((c) => c.from === "edit" && c.field?.startsWith(`${record}.`))
      .filter((c) => c.affordances.some((a) => a === "write" || a === "choose" || a === "adjust"))
      .map((c) => {
        const name = c.field!.slice(record.length + 1);
        return { field: c.field!, record, name, type: c.type ?? "data", secret: this.records.isSecret(record, name) };
      });
  }
}

function compileAddress(address: string): { pattern: RegExp; params: string[] } {
  const params: string[] = [];
  const source = address
    .split(/(\{[^}]+\})/)
    .map((part) => {
      const m = /^\{([^}]+)\}$/.exec(part);
      if (m) {
        params.push(m[1]!);
        return "([^/]+)";
      }
      return part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    })
    .join("");
  return { pattern: new RegExp(`^${source}/?$`), params };
}

/** A label as a plain string, when it is one: a literal, or a message key's key. */
export function labelText(label: Label): string {
  if (typeof label === "string") return label;
  if ("t" in label) return label.t;
  return label.field;
}

// ── the reel ─────────────────────────────────────────────────────────────────

export interface Visit {
  n: number;
  tape: string;
  args: JsonObject;
  /** The documents of this visit by slot (a record name, or `Item[]` for a list). */
  docs: Map<string, DocRef>;
}

export interface Step {
  visit: Visit;
  frame: number;
  /** Whether the frame was entered (its loader ran). A destination put beneath a linked frame is not, until the user goes back to it. */
  entered: boolean;
}

export interface CallFrame {
  tape: string;
  /** Where the call returns to, with the history and root it had. */
  caller: Step;
  history: Step[];
  root: string | null;
  then?: string;
}

interface Stack {
  head: Step;
  history: Step[];
}

/** Where a reel is, kept aside so a move can be undone. */
export interface ReelState {
  head: Step;
  history: Step[];
  root: string | null;
  calls: CallFrame[];
  stacks: Map<string, Stack>;
}

/** One session's journey. The methods change where it is; the session enters frames and holds documents. */
export class Reel {
  head!: Step;
  history: Step[] = [];
  /** The hub destination the history began at, or null. */
  root: string | null = null;
  calls: CallFrame[] = [];
  private stacks = new Map<string, Stack>();
  private visits = 0;

  constructor(private readonly places: Places) {}

  save(): ReelState {
    return { head: this.head, history: [...this.history], root: this.root, calls: [...this.calls], stacks: new Map(this.stacks) };
  }

  restore(state: ReelState): void {
    this.head = state.head;
    this.history = [...state.history];
    this.root = state.root;
    this.calls = [...state.calls];
    this.stacks = new Map(state.stacks);
  }

  /** The journey as a kept one keeps it: positions and history only, never documents (Q69). */
  kept(): Omit<KeptJourney, "user" | "device" | "savedAt"> {
    const step = (s: Step): KeptStep => ({
      visit: s.visit.n, tape: s.visit.tape, frame: this.places.frame(s.visit.tape, s.frame).id ?? null, args: structuredClone(s.visit.args),
    });
    return {
      head: step(this.head),
      history: this.history.map(step),
      root: this.root,
      calls: this.calls.map((c) => ({ tape: c.tape, ...(c.then ? { then: c.then } : {}), caller: step(c.caller), history: c.history.map(step), root: c.root })),
      stacks: [...this.stacks].map(([tape, st]) => ({ tape, head: step(st.head), history: st.history.map(step) })),
    };
  }

  /**
   * Takes up a kept journey: the same places, in new tape visits with their arguments and no
   * documents, none of them entered, so each frame's loader runs when the user gets there. False,
   * with the reel unchanged, when a place it names no longer exists.
   */
  resume(kept: Omit<KeptJourney, "user" | "device" | "savedAt">): boolean {
    const places = this.places;
    const all = [kept.head, ...kept.history, ...kept.calls.flatMap((c) => [c.caller, ...c.history]), ...kept.stacks.flatMap((s) => [s.head, ...s.history])];
    const index = (s: KeptStep) => (s.frame === null ? (places.hasTape(s.tape) && places.tape(s.tape).frames.length === 1 ? 0 : -1) : places.hasTape(s.tape) ? places.frameIndex(s.tape, s.frame) : -1);
    if (all.some((s) => index(s) < 0)) return false;
    const visits = new Map<number, Visit>();
    const step = (s: KeptStep): Step => {
      let v = visits.get(s.visit);
      if (!v) visits.set(s.visit, (v = this.visit(s.tape, structuredClone(s.args))));
      return this.step(v, index(s));
    };
    this.head = step(kept.head);
    this.history = kept.history.map(step);
    this.root = kept.root;
    this.calls = kept.calls.map((c) => ({ tape: c.tape, ...(c.then ? { then: c.then } : {}), caller: step(c.caller), history: c.history.map(step), root: c.root }));
    this.stacks = new Map(kept.stacks.map((st) => [st.tape, { head: step(st.head), history: st.history.map(step) }]));
    return true;
  }

  visit(tape: string, args: JsonObject = {}): Visit {
    return { n: ++this.visits, tape, args, docs: new Map() };
  }

  step(visit: Visit, frame = 0): Step {
    return { visit, frame, entered: false };
  }

  get frame(): Frame {
    return this.places.frame(this.head.visit.tape, this.head.frame);
  }

  get place(): string {
    return this.places.place(this.head.visit.tape, this.head.frame);
  }

  /** Starts over at `tape` as a history root: the entry, a sign-in or sign-out target. */
  start(tape: string, args: JsonObject = {}, frame = 0): void {
    this.history = [];
    this.calls = [];
    this.stacks.clear();
    this.head = this.step(this.visit(tape, args), frame);
    this.root = this.places.isDestination(tape) && frame === 0 ? tape : null;
  }

  /** Opens a frame by its address (Q48): beneath it, the destination the intent names (`under`). */
  open(tape: string, frame: number, args: JsonObject): void {
    this.start(tape, args, frame);
    const under = this.places.frame(tape, frame).under;
    if (under !== undefined) {
      this.history = [this.step(this.visit(under))];
      this.root = under;
    }
  }

  jump(tape: string, args: JsonObject): void {
    this.history.push(this.head);
    this.head = this.step(this.visit(tape, args));
  }

  goto(frame: number): void {
    this.history.push(this.head);
    this.head = this.step(this.head.visit, frame);
  }

  /** The history starts again here: an outcome that signs in or out without moving. */
  reset(): void {
    this.history = [];
    this.calls = [];
    this.stacks.clear();
    this.root = this.places.isDestination(this.head.visit.tape) && this.head.frame === 0 ? this.head.visit.tape : null;
  }

  /** Whether back goes anywhere from here: there is history (or a call to leave), and the frame allows it. */
  get canGoBack(): boolean {
    if (this.frame.back === false) return false;
    return this.history.length > 0 || this.calls.length > 0;
  }

  /** Goes back; leaving a call's first frame ends the call without a result. */
  back(): "back" | "left-call" | "none" {
    if (!this.canGoBack) return "none";
    const prev = this.history.pop();
    if (prev) {
      this.head = prev;
      return "back";
    }
    const call = this.calls.pop()!;
    this.head = call.caller;
    this.history = call.history;
    this.root = call.root;
    return "left-call";
  }

  call(tape: string, args: JsonObject, then: string | undefined): void {
    this.calls.push({ tape, caller: this.head, history: this.history, root: this.root, ...(then ? { then } : {}) });
    this.history = [];
    this.root = null;
    this.head = this.step(this.visit(tape, args));
  }

  /** Ends the innermost call and returns to its caller; says which handler takes the result. */
  done(): { then?: string } | undefined {
    const call = this.calls.pop();
    if (!call) return undefined;
    this.head = call.caller;
    this.history = call.history;
    this.root = call.root;
    return call.then ? { then: call.then } : {};
  }

  /** Whether the frame shows the hub (Q32): its history began at a destination, outside calls. */
  get showsHub(): boolean {
    return this.places.destinations.length > 0 && this.calls.length === 0 && this.root !== null && this.frame.hub !== false;
  }

  /** Moves to a hub destination, keeping each destination's own history; the current one starts over. */
  door(tape: string): void {
    if (this.root !== null) this.stacks.set(this.root, { head: this.head, history: this.history });
    const saved = tape === this.root ? undefined : this.stacks.get(tape);
    this.stacks.delete(tape);
    if (saved) {
      this.head = saved.head;
      this.history = saved.history;
    } else {
      this.head = this.step(this.visit(tape));
      this.history = [];
    }
    this.root = tape;
  }

  /** Every visit the reel still holds: their documents stay alive. */
  live(): Set<Visit> {
    const out = new Set<Visit>();
    const add = (s: Step) => out.add(s.visit);
    add(this.head);
    this.history.forEach(add);
    for (const c of this.calls) {
      add(c.caller);
      c.history.forEach(add);
    }
    for (const s of this.stacks.values()) {
      add(s.head);
      s.history.forEach(add);
    }
    return out;
  }

  /** Where the reel is, for readers: places by name. */
  describe(): ReelView {
    const name = (s: Step) => this.places.place(s.visit.tape, s.frame);
    return {
      head: name(this.head),
      history: this.history.map(name),
      root: this.history.length === 0 && this.calls.length === 0,
      back: this.canGoBack,
      hub: this.showsHub ? { destinations: [...this.places.destinations], current: this.root! } : null,
      calls: this.calls.map((c) => c.tape),
      args: { ...this.head.visit.args },
    };
  }
}

export interface ReelView {
  head: string;
  history: string[];
  /** The head is a history root: nothing to go back to. */
  root: boolean;
  back: boolean;
  hub: { destinations: string[]; current: string } | null;
  calls: string[];
  args: JsonObject;
}

export type { Json };
