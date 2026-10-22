// VTP/1: the WebSocket message set between player and engine (spec §9).
// Both ends validate every message with these schemas, so they cannot drift.

import { z } from "zod";
import { COMPONENT_KINDS } from "./model";
import { VIEWPORT_CLASSES } from "./viewport";

export const VTP_VERSION = 1;
/** Largest string value the engine accepts in an event (spec §10). */
export const MAX_VALUE_BYTES = 4096;
/** Largest message, in characters, either side will parse. */
export const MAX_MESSAGE_CHARS = 256 * 1024;

const seq = z.number().int().nonnegative();
const rect = z.tuple([z.number(), z.number(), z.number(), z.number()]);
const viewport = z.object({ w: z.number().positive().max(16384), h: z.number().positive().max(16384), dpr: z.number().positive().max(8) });
const head = z.object({ tape: z.string(), frame: z.string() });
const scalar = z.union([z.string().max(MAX_VALUE_BYTES), z.number().finite(), z.boolean()]);

// ── client → server ─────────────────────────────────────────────────────────

export const HelloSchema = z.object({
  t: z.literal("hello"),
  v: z.literal(VTP_VERSION),
  viewport,
  caps: z.object({ video: z.array(z.enum(["webm", "mp4"])), webrtc: z.boolean() }),
  resume: z.string().max(128).optional(),
});

export const EventSchema = z.object({
  t: z.literal("event"),
  seq,
  /** The `seq` of the render this event was made against. */
  render: seq,
  component: z.string().max(64),
  type: z.string().max(32),
  value: scalar.optional(),
  values: z.record(z.string().max(64), scalar).optional(),
});

export const ResizeSchema = z.object({ t: z.literal("resize"), viewport });
export const RerollSchema = z.object({ t: z.literal("reroll"), frame: z.string().optional() });
export const PingSchema = z.object({ t: z.literal("ping") });

export const ClientMessageSchema = z.discriminatedUnion("t", [HelloSchema, EventSchema, ResizeSchema, RerollSchema, PingSchema]);
export type ClientMessage = z.infer<typeof ClientMessageSchema>;
export type HelloMessage = z.infer<typeof HelloSchema>;
export type EventMessage = z.infer<typeof EventSchema>;

// ── server → client ─────────────────────────────────────────────────────────

const palette = z.object({ bg: z.string(), fg: z.string(), accent: z.string(), muted: z.string() });

export const WelcomeSchema = z.object({
  t: z.literal("welcome"),
  session: z.string(),
  token: z.string(),
  viewportClass: z.enum(VIEWPORT_CLASSES),
  canvas: z.object({ w: z.number(), h: z.number() }),
  style: z.object({ id: z.string(), palette, fonts: z.object({ display: z.string(), body: z.string() }) }),
  debug: z.boolean().optional(),
});

export const LayerSchema = z.object({ kind: z.enum(["image", "video"]), url: z.string(), z: z.number().int() });
export type Layer = z.infer<typeof LayerSchema>;

export const RegionSchema = z.object({
  id: z.string(),
  kind: z.string(),
  rect,
  mask: z.enum(["reserved", "surface", "free"]),
  z: z.number().int().optional(),
});

export const TypeHintSchema = z.object({
  role: z.enum(["display", "title", "subtitle", "body", "caption", "number", "control"]),
  size: z.number(),
  lines: z.number().int(),
  align: z.enum(["start", "center"]),
});

const listItem = z.object({ id: z.string(), label: z.string(), meta: z.string().optional() });
const option = z.object({ value: z.string(), label: z.string() });

/** One node of the content layer: a fact or a control, placed over the scene. */
export const ContentSchema = z.object({
  id: z.string(),
  kind: z.enum(COMPONENT_KINDS),
  rect,
  type: TypeHintSchema.optional(),
  labelSize: z.number().optional(),
  variant: z.string().optional(),
  value: z.union([z.string(), z.number(), z.boolean(), z.null()]).optional(),
  label: z.string().optional(),
  inputType: z.enum(["text", "secret", "email", "number", "search"]).optional(),
  placeholder: z.string().optional(),
  emphasis: z.enum(["primary", "secondary"]).optional(),
  commit: z.enum(["submit", "blur", "change"]).optional(),
  items: z.array(listItem).optional(),
  options: z.array(option).optional(),
  src: z.string().optional(),
  alt: z.string().optional(),
  media: z.enum(["video", "audio"]).optional(),
  min: z.number().optional(),
  max: z.number().optional(),
  step: z.number().optional(),
  a11y: z.object({ label: z.string().optional(), role: z.string().optional() }).optional(),
});
export type Content = z.infer<typeof ContentSchema>;

export const EdgeSchema = z.object({
  component: z.string(),
  event: z.string(),
  kind: z.enum(["goto", "jump", "back", "stay"]),
  to: head.optional(),
  handler: z.string().optional(),
  cut: z.string().optional(),
});
export type Edge = z.infer<typeof EdgeSchema>;

export const RenderSchema = z.object({
  t: z.literal("render"),
  seq,
  head,
  key: z.string(),
  layers: z.array(LayerSchema),
  regions: z.array(RegionSchema),
  content: z.array(ContentSchema),
  edges: z.array(EdgeSchema),
  a11y: z.object({ title: z.string() }),
  fallback: z.boolean(),
  /** Debug details for the HUD; present only when the engine runs with debug on. */
  debug: z.record(z.string(), z.unknown()).optional(),
});
export type RenderMessage = z.infer<typeof RenderSchema>;

export const CutSchema = z.object({
  t: z.literal("cut"),
  seq,
  from: z.string(),
  to: z.string(),
  url: z.string().optional(),
  durationMs: z.number().int().nonnegative(),
  kind: z.enum(["generated", "crossfade"]),
});

export const ContentPatchSchema = ContentSchema.partial().extend({ id: z.string() });

export const PatchSchema = z.object({
  t: z.literal("patch"),
  seq,
  /** The render this patch applies to. */
  render: seq,
  content: z.array(ContentPatchSchema).optional(),
  layers: z.array(LayerSchema).optional(),
  key: z.string().optional(),
  fallback: z.boolean().optional(),
});

export const PrefetchSchema = z.object({
  t: z.literal("prefetch"),
  assets: z.array(z.object({ url: z.string(), kind: z.enum(["scene", "cut", "ambient"]), forEdge: z.string() })),
});

export const ErrorSchema = z.object({
  t: z.literal("error"),
  code: z.string(),
  message: z.string(),
  recoverable: z.boolean(),
});

export const PongSchema = z.object({ t: z.literal("pong") });

export const ServerMessageSchema = z.discriminatedUnion("t", [
  WelcomeSchema, RenderSchema, CutSchema, PatchSchema, PrefetchSchema, ErrorSchema, PongSchema,
]);
export type ServerMessage = z.infer<typeof ServerMessageSchema>;
export type WelcomeMessage = z.infer<typeof WelcomeSchema>;
export type CutMessage = z.infer<typeof CutSchema>;
export type PatchMessage = z.infer<typeof PatchSchema>;
export type PrefetchMessage = z.infer<typeof PrefetchSchema>;
export type ErrorMessage = z.infer<typeof ErrorSchema>;

/** Parses raw text into a message, or returns the reason it was rejected. */
export function decode<T>(schema: z.ZodType<T>, raw: string): { ok: true; msg: T } | { ok: false; reason: string } {
  if (raw.length > MAX_MESSAGE_CHARS) return { ok: false, reason: "message too large" };
  let json: unknown;
  try {
    json = JSON.parse(raw);
  } catch {
    return { ok: false, reason: "not JSON" };
  }
  const r = schema.safeParse(json);
  return r.success ? { ok: true, msg: r.data } : { ok: false, reason: r.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ") };
}
