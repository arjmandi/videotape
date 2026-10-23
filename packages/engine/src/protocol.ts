// The app protocol (05 §6.6, §14): engine ↔ app process, JSON over a WebSocket. The app connects
// out to the engine, registers its intent, answers `load`, `page`, and `decide`, and sends document
// changes as `sync`. Every message the app sends is validated here before the engine reads it;
// the shapes are written down in the package README.

import { z } from "zod";
import type { Json, JsonObject, Label } from "./intent";
import type { PathSegment } from "./records";

export const APP_PROTOCOL_VERSION = 1;
/** Largest message, in characters, the engine parses. */
export const MAX_MESSAGE_CHARS = 16 * 1024 * 1024;

// ── documents on the wire ────────────────────────────────────────────────────

const name = z.string().min(1).max(256);
/** A shared document is addressed by its record and `vt.Id`; a session's own by the engine's key. */
export const DocRefSchema = z.union([
  z.object({ record: name, id: z.string().max(1024) }).strict(),
  z.object({ record: name, local: name }).strict(),
]);
export type DocRef = z.infer<typeof DocRefSchema>;

const segment = z.union([z.string().min(1).max(256), z.object({ key: z.string().min(1).max(1024) }).strict()]);
const path = z.array(segment).max(64);
const at = z.union([
  z.literal("end"),
  z.literal("start"),
  z.object({ before: z.string().min(1) }).strict(),
  z.object({ after: z.string().min(1) }).strict(),
]);

export const OpSchema = z.discriminatedUnion("op", [
  z.object({ op: z.literal("set"), path, value: z.unknown() }).strict(),
  z.object({ op: z.literal("insert"), path, key: z.string().min(1).max(1024), value: z.unknown(), at: at.optional() }).strict(),
  z.object({ op: z.literal("remove"), path, key: z.string().min(1).optional(), id: z.string().min(1).optional() }).strict(),
  z.object({ op: z.literal("replace"), path, key: z.string().min(1).optional(), id: z.string().min(1).optional(), value: z.unknown() }).strict(),
]);
export type Op = z.infer<typeof OpSchema>;
export type At = z.infer<typeof at>;

export const ChangeSchema = z.object({ doc: DocRefSchema, ops: z.array(OpSchema).min(1).max(10_000) }).strict();
export type Change = z.infer<typeof ChangeSchema>;

// ── app → engine ─────────────────────────────────────────────────────────────

export const RegisterSchema = z.object({
  t: z.literal("register"),
  v: z.literal(APP_PROTOCOL_VERSION),
  intent: z.record(z.unknown()),
  sdk: z.object({ language: z.string().max(64), version: z.string().max(64) }).passthrough(),
}).strict();

const label: z.ZodType<Label> = z.union([
  z.string(),
  z.object({ t: z.string(), params: z.record(z.unknown()).optional() }).strict() as z.ZodType<{ t: string; params?: JsonObject }>,
  z.object({ field: z.string() }).strict(),
]);
const loaded = z.union([
  z.object({ record: name, value: z.record(z.unknown()) }).strict(),
  z.object({ collection: name.nullable(), value: z.array(z.unknown()) }).strict(),
]);
const id = z.string().min(1).max(64);

export const ResultSchema = z.union([
  z.object({ t: z.literal("result"), id, outcome: z.object({ type: z.string() }).passthrough() }).strict(),
  z.object({ t: z.literal("result"), id, reject: z.object({ message: label }).strict() }).strict(),
  z.object({ t: z.literal("result"), id, documents: z.array(loaded).max(64) }).strict(),
  z.object({ t: z.literal("result"), id, page: z.object({ items: z.array(z.unknown()), next: z.string().nullable() }).strict() }).strict(),
  z.object({ t: z.literal("result"), id, error: z.object({ type: z.string().max(256), message: z.string().max(8192) }).strict() }).strict(),
]);

export const SyncSchema = z.object({
  t: z.literal("sync"),
  changes: z.array(ChangeSchema).min(1).max(1000),
  /** The decision these changes are tentative under; without it they are confirmed at once. */
  decision: id.optional(),
}).strict();

export const LogSchema = z.object({
  t: z.literal("log"),
  level: z.enum(["debug", "info", "warning", "error"]),
  message: z.string().max(65_536),
  logger: z.string().max(256).optional(),
}).strict();

export const PingSchema = z.object({ t: z.literal("ping") }).strict();

export const AppMessageSchema = z.union([RegisterSchema, ResultSchema, SyncSchema, LogSchema, PingSchema]);
export type AppMessage = z.infer<typeof AppMessageSchema>;
export type RegisterMessage = z.infer<typeof RegisterSchema>;
export type ResultMessage = z.infer<typeof ResultSchema>;
export type SyncMessage = z.infer<typeof SyncSchema>;
export type LogMessage = z.infer<typeof LogSchema>;
export type Loaded = z.infer<typeof loaded>;

// ── engine → app ─────────────────────────────────────────────────────────────

/** The signed-in user's record, as `ctx.user` (05 §6.2). */
export interface UserRecord {
  record: string;
  id: string;
  value: JsonObject;
}

/** A document a loader or handler receives: a whole document, or an item at `path` in one. */
export interface DocValue {
  ref: DocRef;
  value: Json;
  path?: PathSegment[];
  record?: string;
}

export interface LoadRequest {
  t: "load";
  id: string;
  loader: string;
  session: string;
  user: UserRecord | null;
  args: JsonObject;
  documents: Record<string, DocValue>;
}

export interface PageRequest {
  t: "page";
  id: string;
  loader: string;
  session: string;
  user: UserRecord | null;
  cursor: string | null;
  documents: Record<string, DocValue>;
}

export interface DecideRequest {
  t: "decide";
  id: string;
  handler: string;
  session: string;
  user: UserRecord | null;
  documents: Record<string, DocValue>;
  /** Parameters that are not documents: a call's `result`, a move's target. */
  values?: JsonObject;
}

export type AppRequest = LoadRequest | PageRequest | DecideRequest;

export type EngineMessage =
  | { t: "registered"; v: number; app: string }
  | { t: "error"; code: string; message: string }
  | { t: "pong" }
  | AppRequest;

/** Parses raw text into a message from the app, or says why it was refused (never echoing content). */
export function decodeAppMessage(raw: string): { ok: true; msg: AppMessage } | { ok: false; reason: string } {
  if (raw.length > MAX_MESSAGE_CHARS) return { ok: false, reason: "message too large" };
  let json: unknown;
  try {
    json = JSON.parse(raw);
  } catch {
    return { ok: false, reason: "not JSON" };
  }
  const r = AppMessageSchema.safeParse(json);
  if (r.success) return { ok: true, msg: r.data };
  const t = typeof json === "object" && json !== null && "t" in json ? String((json as { t: unknown }).t).slice(0, 32) : "?";
  return { ok: false, reason: `not a valid ${t} message` };
}
