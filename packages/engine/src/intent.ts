// Intent: the JSON an SDK produces for an app (05 §6), read and checked before the engine plays it.
// The document is validated against the schema the Python SDK publishes
// (sdk/python/src/videotape/intent.schema.json), then every name it uses is resolved, so the
// journey runtime can trust what it looks up.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { ValidateFunction } from "ajv";
import { Ajv2020 } from "ajv/dist/2020.js";

export const INTENT_FORMAT = "videotape.intent/2";

/** The schema the Python SDK publishes; the engine reads the same file, so the two cannot drift. */
export const INTENT_SCHEMA_PATH = fileURLToPath(new URL("../../../sdk/python/src/videotape/intent.schema.json", import.meta.url));

// ── the document ─────────────────────────────────────────────────────────────

export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
export type JsonObject = { [key: string]: Json };

/** Copy: a literal, a message key with parameters (`vt.t`), or a field reference. */
export type Label = string | { t: string; params?: JsonObject } | FieldRef;
export interface FieldRef {
  field: string;
}

export interface HandlerRef {
  handler: string;
}

export interface Jump {
  type: "jump";
  tape: string;
  args?: JsonObject;
  sign_in?: Json;
  sign_out?: boolean;
}
export interface Goto {
  type: "goto";
  frame: string;
  sign_in?: Json;
  sign_out?: boolean;
}
export interface Back {
  type: "back";
  sign_in?: Json;
  sign_out?: boolean;
}
export interface Stay {
  type: "stay";
  sign_in?: Json;
  sign_out?: boolean;
}
export interface Call {
  type: "call";
  tape: string;
  args?: JsonObject;
  then?: HandlerRef;
}
export interface Done {
  type: "done";
  result?: Json;
}
export interface Open {
  type: "open";
  url: Json;
}
export interface Download {
  type: "download";
  name: string;
  data: string;
  encoding?: "base64";
}
export interface Copy {
  type: "copy";
  field?: string;
  text?: string;
}
export type Outcome = Jump | Goto | Back | Stay | Call | Done | Open | Download | Copy;
/** What an action, a select, or a press does: an outcome as data, or the handler that decides. */
export type Target = Outcome | HandlerRef;

export interface Action {
  label: Label;
  target: Target;
  affordance: string;
  on?: string | FieldRef;
  to?: string;
  gesture?: string;
  key?: string;
  role?: string;
  importance?: string;
  hidden?: FieldRef;
  visible?: FieldRef;
}

export interface Kind {
  type: string;
  record?: string;
  enum?: string;
  choices?: Json[];
  lines?: [number, number];
  item?: Kind & { components?: Component[]; states?: string[] };
  nullable?: boolean;
}

export interface Component extends Partial<Kind> {
  field?: string;
  text?: string | { t: string; params?: JsonObject };
  from?: "shows" | "edit";
  role?: string;
  importance?: string;
  select?: Target;
  press?: Target;
  pages?: { loader: string };
  affordances: string[];
  many?: boolean;
  components?: Component[];
  states?: string[];
  override?: boolean;
  [option: string]: unknown;
}

export interface Shows {
  record?: string;
  collection?: string;
}

export interface Frame {
  id?: string;
  purpose: string;
  title?: Label;
  address?: string;
  public?: boolean;
  shows?: Shows[];
  edit?: { record: string };
  enter?: { loader: string };
  submit?: { label: Label; handler: string };
  components: Component[];
  states?: string[];
  actions?: Action[];
  on_change?: Array<{ field: string; handler: string }>;
  after?: { seconds: number; then: Target };
  back?: boolean;
  hub?: boolean;
  under?: string;
  root?: "always" | "sometimes";
}

export interface Tape {
  id: string;
  frames: Frame[];
}

export interface Destination {
  tape: string;
  label: Label;
  symbol?: string;
}

export interface Param extends Kind {
  name: string;
  required: boolean;
  default?: Json;
}

export interface Declared {
  type: string;
  tape?: string;
  frame?: string;
  args?: string[];
  args_open?: boolean;
  resets_history?: boolean;
  signs_in?: boolean;
  then?: HandlerRef;
  implied?: boolean;
}

export interface Handler {
  params: Param[];
  outcomes: Declared[];
  unreadable?: string;
}

export interface Loader {
  params: Param[];
  returns?: Kind[];
  unreadable?: string;
}

export interface Edge {
  from: string;
  to?: string;
  type: string;
  tape?: string;
  frame?: string;
  resets_history?: boolean;
  signs_in?: boolean;
  via: JsonObject;
}

/** A record's JSON Schema, as Pydantic writes it, with Videotape's options under `x-vt`. */
export interface RecordSchema {
  type?: string;
  enum?: Json[];
  properties?: Record<string, PropertySchema>;
  required?: string[];
  "x-vt"?: { type: string; id?: string };
  [keyword: string]: unknown;
}
export interface PropertySchema {
  "x-vt"?: Kind & { state?: boolean; [option: string]: unknown };
  default?: Json;
  [keyword: string]: unknown;
}

export interface Intent {
  format: typeof INTENT_FORMAT;
  app: string;
  entry: string;
  world?: string;
  hub?: Destination[];
  tapes: Tape[];
  records: Record<string, RecordSchema>;
  types: Record<string, JsonObject>;
  handlers: Record<string, Handler>;
  loaders: Record<string, Loader>;
  edges: Edge[];
}

// ── loading ──────────────────────────────────────────────────────────────────

export class IntentError extends Error {
  constructor(readonly issues: string[]) {
    super(`the intent cannot be played:\n${issues.map((i) => `  ${i}`).join("\n")}`);
    this.name = "IntentError";
  }
}

let schemaValidator: ValidateFunction | undefined;

function validateAgainstSchema(value: unknown): string[] {
  if (!schemaValidator) {
    const schema = JSON.parse(readFileSync(INTENT_SCHEMA_PATH, "utf8")) as object;
    schemaValidator = new Ajv2020({ strict: false, validateFormats: false }).compile(schema);
  }
  const validate = schemaValidator;
  if (validate(value)) return [];
  return (validate.errors ?? []).slice(0, 10).map((e) => `schema: ${e.instancePath || "/"} ${e.message ?? "is invalid"}`);
}

/** Reads an intent document (JSON text or a parsed value), validates it, and resolves its names. */
export function loadIntent(input: string | unknown): Intent {
  let value: unknown = input;
  if (typeof input === "string") {
    try {
      value = JSON.parse(input);
    } catch (e) {
      throw new IntentError([`not JSON: ${e instanceof Error ? e.message : String(e)}`]);
    }
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new IntentError(["the intent is not a JSON object"]);
  const format = (value as { format?: unknown }).format;
  if (format !== INTENT_FORMAT) throw new IntentError([`format is ${JSON.stringify(format)}; this engine plays ${INTENT_FORMAT}`]);
  const schemaIssues = validateAgainstSchema(value);
  if (schemaIssues.length) throw new IntentError(schemaIssues);
  const intent = value as Intent;
  const issues = resolveNames(intent);
  if (issues.length) throw new IntentError(issues);
  return intent;
}

export function loadIntentFile(path: string): Intent {
  return loadIntent(readFileSync(path, "utf8"));
}

/** The node name a frame has in the journey graph: `tape`, or `tape/id` in a tape of several. */
export function placeName(tape: Tape, frame: Frame): string {
  return tape.frames.length > 1 || frame.id ? `${tape.id}/${frame.id ?? ""}` : tape.id;
}

function isHandlerRef(t: Target): t is HandlerRef {
  return "handler" in t;
}

/** Every name the runtime will look up must exist; `videotape check` reports the same, but the
 *  engine never trusts its input to have been checked. */
function resolveNames(intent: Intent): string[] {
  const issues: string[] = [];
  const tapes = new Map<string, Tape>();
  const addresses = new Set<string>();
  for (const t of intent.tapes) {
    if (tapes.has(t.id)) issues.push(`two tapes are named ${t.id}`);
    tapes.set(t.id, t);
    if (t.frames.length === 0) issues.push(`tape ${t.id} has no frames`);
    const ids = new Set<string>();
    for (const f of t.frames) {
      if (t.frames.length > 1 && !f.id) issues.push(`a frame of ${t.id} has no id, and the tape has several`);
      if (f.id) {
        if (ids.has(f.id)) issues.push(`tape ${t.id} has two frames named ${f.id}`);
        ids.add(f.id);
      }
      if (f.address) {
        if (addresses.has(f.address)) issues.push(`two frames have the address ${f.address}`);
        addresses.add(f.address);
      }
    }
  }
  const record = (name: string | undefined, where: string) => {
    if (name !== undefined && !(name in intent.records)) issues.push(`${where} names the record ${name}, which the intent does not carry`);
  };
  const handler = (name: string, where: string) => {
    if (!(name in intent.handlers)) issues.push(`${where} names the handler ${name}, which the intent does not carry`);
  };
  const loader = (name: string, where: string) => {
    if (!(name in intent.loaders)) issues.push(`${where} names the loader ${name}, which the intent does not carry`);
  };
  const outcome = (o: Outcome, tape: Tape, where: string) => {
    if ((o.type === "jump" || o.type === "call") && !tapes.has(o.tape)) issues.push(`${where} goes to the tape ${o.tape}, which does not exist`);
    if (o.type === "goto" && !tape.frames.some((f) => f.id === o.frame)) issues.push(`${where} goes to the frame ${o.frame}, which ${tape.id} does not have`);
    if (o.type === "call" && o.then) handler(o.then.handler, where);
  };
  const target = (t: Target, tape: Tape, where: string) => (isHandlerRef(t) ? handler(t.handler, where) : outcome(t, tape, where));

  if (!tapes.has(intent.entry)) issues.push(`the entry tape ${intent.entry} does not exist`);
  for (const d of intent.hub ?? []) if (!tapes.has(d.tape)) issues.push(`the hub names the tape ${d.tape}, which does not exist`);
  const hubTapes = new Set((intent.hub ?? []).map((d) => d.tape));
  for (const t of intent.tapes) {
    for (const f of t.frames) {
      const where = placeName(t, f);
      for (const s of f.shows ?? []) record(s.record ?? s.collection, where);
      record(f.edit?.record, where);
      if (f.enter) loader(f.enter.loader, where);
      if (f.submit) handler(f.submit.handler, where);
      for (const a of f.actions ?? []) target(a.target, t, `${where} (action ${JSON.stringify(a.label)})`);
      if (f.after) target(f.after.then, t, `${where} (timer)`);
      for (const c of f.on_change ?? []) handler(c.handler, where);
      if (f.under !== undefined && !hubTapes.has(f.under)) issues.push(`${where} is under ${f.under}, which is not a hub destination`);
      const walk = (components: Component[]) => {
        for (const c of components) {
          if (c.select) target(c.select, t, `${where} (${c.field ?? "component"})`);
          if (c.press) target(c.press, t, `${where} (${c.field ?? "component"})`);
          if (c.pages) loader(c.pages.loader, where);
          if (c.components) walk(c.components);
          if (c.item?.components) walk(c.item.components);
        }
      };
      walk(f.components);
    }
  }
  for (const [name, r] of Object.entries(intent.records)) {
    const id = r["x-vt"]?.id;
    if (id !== undefined && !(id in (r.properties ?? {}))) issues.push(`record ${name} names ${id} as its id, which it does not have`);
  }
  return issues;
}
