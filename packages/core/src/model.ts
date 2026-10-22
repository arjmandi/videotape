// The tape model and its TypeScript authoring API (spec §5.1).
//
// Builders return plain objects that carry both the serialisable spec and the
// app's functions (handlers, enter hooks, flavour and scene functions). `toSpec`
// in ./serialize strips the functions to produce the wire format.

import type { StylePack } from "./style";
import type { ViewportClass } from "./viewport";

/** Reel data. Typed loosely on purpose: it is app-defined JSON. */
export type Data = Record<string, any>;

/** A map of path → value, applied with `setPath` (spec §5.2, Patches). */
export type DataPatch = Record<string, unknown>;

/**
 * Services injected into handlers and enter hooks. Apps add typed members by
 * declaration merging: `declare module "@videotape/core" { interface Services { auth: Auth } }`.
 */
export interface Services {
  [name: string]: any;
}

// ── bind ────────────────────────────────────────────────────────────────────

export interface Bind {
  readonly bind: string;
}

export function bind(path: string): Bind {
  return { bind: path };
}

export function isBind(value: unknown): value is Bind {
  return typeof value === "object" && value !== null && typeof (value as Bind).bind === "string";
}

// ── actions ─────────────────────────────────────────────────────────────────

export interface GotoAction { type: "goto"; frame: string }
export interface JumpAction { type: "jump"; tape: string; data?: DataPatch }
export interface BackAction { type: "back" }
export interface StayAction { type: "stay"; patch?: DataPatch }

export type Action = GotoAction | JumpAction | BackAction | StayAction;
/** Actions a component may name directly; `stay` only comes from handlers. */
export type StaticAction = GotoAction | JumpAction | BackAction;
/** A static action, or the name of a frame handler. */
export type ActionRef = StaticAction | string;

export function goto(frame: string): GotoAction {
  return { type: "goto", frame };
}

export function jump(tape: string, data?: DataPatch): JumpAction {
  return data === undefined ? { type: "jump", tape } : { type: "jump", tape, data };
}

export function back(): BackAction {
  return { type: "back" };
}

export function stay(patch?: DataPatch): StayAction {
  return patch === undefined ? { type: "stay" } : { type: "stay", patch };
}

// ── handlers, hooks ─────────────────────────────────────────────────────────

export interface Head {
  tape: string;
  frame: string;
}

export interface ReelInfo {
  session: string;
  head: Head;
  history: readonly Head[];
  viewportClass: ViewportClass;
}

export interface HandlerContext {
  /** Committed values keyed by component id; `item` for a list `select`. */
  values: Record<string, any>;
  /** The event's own value, if it carries one. */
  value?: unknown;
  event: { component: string; type: string };
  data: Readonly<Data>;
  services: Services;
  reel: ReelInfo;
}

export type HandlerFn = (ctx: HandlerContext) => Action | Promise<Action>;

export interface Handler {
  readonly kind: "handler";
  fn: HandlerFn;
  /** Declared so the graph knows the edges (spec §5.1). */
  outcomes?: Action[];
}

export function handler(fn: HandlerFn, opts: { outcomes?: Action[] } = {}): Handler {
  return opts.outcomes === undefined ? { kind: "handler", fn } : { kind: "handler", fn, outcomes: opts.outcomes };
}

export interface EnterContext {
  data: Readonly<Data>;
  services: Services;
  reel: ReelInfo;
}

export type EnterFn = (ctx: EnterContext) => DataPatch | void | Promise<DataPatch | void>;
export type Flavour = Record<string, string | number | boolean>;
export type FlavourFn = (data: Readonly<Data>) => Flavour;
export type SceneFn = (flavour: Flavour) => string;

// ── components ──────────────────────────────────────────────────────────────

export const COMPONENT_KINDS = [
  "text", "image", "media", "button", "link", "input", "textarea", "select", "toggle", "slider", "date", "list",
] as const;
export type ComponentKind = (typeof COMPONENT_KINDS)[number];

/** Events each kind emits (spec §5.3). */
export const KIND_EVENTS: Record<ComponentKind, readonly string[]> = {
  text: [], image: [], media: [],
  button: ["press"], link: ["press"],
  input: ["change", "commit"], textarea: ["change", "commit"], slider: ["change", "commit"],
  select: ["change"], toggle: ["change"], date: ["change"],
  list: ["select"],
};

/** Kinds whose value travels with a submit and may be bound two-way. */
export const VALUE_KINDS: readonly ComponentKind[] = ["input", "textarea", "select", "toggle", "slider", "date"];
/** Kinds that must lead somewhere: an action or a handler (spec §5.6). */
export const ACTION_KINDS: readonly ComponentKind[] = ["button", "link", "list"];

export function isInteractive(kind: ComponentKind): boolean {
  return KIND_EVENTS[kind].length > 0;
}

export type Rect = [x: number, y: number, w: number, h: number];
export type TextVariant = "title" | "subtitle" | "body" | "caption" | "number";
export type InputType = "text" | "secret" | "email" | "number" | "search";
export type CommitMode = "submit" | "blur" | "change";

export interface ListItem { id: string; label: string; meta?: string }
export interface SelectOption { value: string; label: string }

interface Base {
  id: string;
  slot?: string;
  /** Required by the `blank` archetype, ignored elsewhere. Canvas fractions. */
  rect?: Rect;
  a11y?: { label?: string; role?: string };
  on?: Partial<Record<string, ActionRef>>;
}

export interface TextComponent extends Base { kind: "text"; value?: string; bind?: string; variant?: TextVariant }
export interface ImageComponent extends Base { kind: "image"; src?: string; bind?: string; alt?: string }
export interface MediaComponent extends Base { kind: "media"; src?: string; bind?: string; media?: "video" | "audio" }
export interface ButtonComponent extends Base { kind: "button"; label: string; emphasis?: "primary" | "secondary" }
export interface LinkComponent extends Base { kind: "link"; label: string }
interface ValueBase extends Base { label: string; bind?: string; commit?: CommitMode }
export interface InputComponent extends ValueBase { kind: "input"; type?: InputType; placeholder?: string }
export interface TextareaComponent extends ValueBase { kind: "textarea"; placeholder?: string }
export interface SelectComponent extends ValueBase { kind: "select"; options: SelectOption[] | Bind }
export interface ToggleComponent extends ValueBase { kind: "toggle" }
export interface SliderComponent extends ValueBase { kind: "slider"; min?: number; max?: number; step?: number }
export interface DateComponent extends ValueBase { kind: "date" }
export interface ListComponent extends Base { kind: "list"; items?: ListItem[]; bind?: string; label?: string }

export type Component =
  | TextComponent | ImageComponent | MediaComponent | ButtonComponent | LinkComponent
  | InputComponent | TextareaComponent | SelectComponent | ToggleComponent | SliderComponent
  | DateComponent | ListComponent;

type Opts<C extends Component, K extends keyof C = never> = Omit<C, "id" | "kind" | K>;

/** Splits a literal-or-bind value into the component's value field or `bind`. */
function valueOrBind<F extends string>(field: F, v: string | Bind): Record<string, string> {
  return isBind(v) ? { bind: v.bind } : { [field]: v };
}

export function text(id: string, value: string | Bind, opts: Opts<TextComponent, "value" | "bind"> = {}): TextComponent {
  return { id, kind: "text", ...valueOrBind("value", value), ...opts };
}

export function image(id: string, src: string | Bind, opts: Opts<ImageComponent, "src" | "bind"> = {}): ImageComponent {
  return { id, kind: "image", ...valueOrBind("src", src), ...opts };
}

export function media(id: string, src: string | Bind, opts: Opts<MediaComponent, "src" | "bind"> = {}): MediaComponent {
  return { id, kind: "media", ...valueOrBind("src", src), ...opts };
}

export function button(id: string, label: string, opts: Opts<ButtonComponent, "label"> = {}): ButtonComponent {
  return { id, kind: "button", label, ...opts };
}

export function link(id: string, label: string, opts: Opts<LinkComponent, "label"> = {}): LinkComponent {
  return { id, kind: "link", label, ...opts };
}

export function input(id: string, opts: Opts<InputComponent>): InputComponent {
  return { id, kind: "input", ...opts };
}

export function textarea(id: string, opts: Opts<TextareaComponent>): TextareaComponent {
  return { id, kind: "textarea", ...opts };
}

export function select(id: string, opts: Opts<SelectComponent>): SelectComponent {
  return { id, kind: "select", ...opts };
}

export function toggle(id: string, opts: Opts<ToggleComponent>): ToggleComponent {
  return { id, kind: "toggle", ...opts };
}

export function slider(id: string, opts: Opts<SliderComponent>): SliderComponent {
  return { id, kind: "slider", ...opts };
}

export function date(id: string, opts: Opts<DateComponent>): DateComponent {
  return { id, kind: "date", ...opts };
}

export function list(
  id: string,
  opts: Omit<ListComponent, "id" | "kind" | "items" | "bind"> & { items: ListItem[] | Bind },
): ListComponent {
  const { items, ...rest } = opts;
  return isBind(items) ? { id, kind: "list", bind: items.bind, ...rest } : { id, kind: "list", items, ...rest };
}

// ── frames, tapes, app ──────────────────────────────────────────────────────

export const ARCHETYPES = ["hero", "form", "list", "detail", "grid", "reader", "blank"] as const;
export type Archetype = (typeof ARCHETYPES)[number];

export type CutHint = "crossfade" | "generated" | "none";

export interface Frame {
  id: string;
  title?: string;
  layout?: Archetype;
  scene?: string | SceneFn;
  flavour?: FlavourFn;
  components: Component[];
  on?: Record<string, Handler>;
  enter?: EnterFn;
  cut?: CutHint;
}

export function frame(id: string, def: Omit<Frame, "id">): Frame {
  return { id, ...def };
}

export interface Tape {
  id: string;
  title?: string;
  style?: string;
  /** Entry frame id; defaults to the first frame. */
  entry?: string;
  frames: Frame[];
}

export function tape(id: string, def: Omit<Tape, "id">): Tape {
  return { id, ...def };
}

export interface App {
  entry: string;
  tapes: Tape[];
  /** Style packs beyond the built-in ones (see ./style). */
  styles?: StylePack[];
}

export function app(def: App): App {
  return def;
}

export const DEFAULT_STYLE = "dusk";

export function tapeEntry(t: Tape): string | undefined {
  return t.entry ?? t.frames[0]?.id;
}
