// Zod schemas for the tape wire format (spec §5.4). Defined once here and
// exported as JSON Schema by ./jsonschema.

import { z } from "zod";
import { ARCHETYPES } from "./model";

const id = z.string().min(1).max(64).regex(/^[A-Za-z][\w-]*$/, "ids start with a letter and use letters, digits, _ or -");
const path = z.string().min(1).max(256).regex(/^[A-Za-z_$][\w$]*(\.[A-Za-z_$][\w$]*)*$/, "a dotted data path");
const dataPatch = z.record(z.string(), z.unknown());

export const ActionSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("goto"), frame: id }),
  z.object({ type: z.literal("jump"), tape: id, data: dataPatch.optional() }),
  z.object({ type: z.literal("back") }),
  z.object({ type: z.literal("stay"), patch: dataPatch.optional() }),
]);
export type ActionSpec = z.infer<typeof ActionSchema>;

const StaticActionSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("goto"), frame: id }),
  z.object({ type: z.literal("jump"), tape: id, data: dataPatch.optional() }),
  z.object({ type: z.literal("back") }),
]);
const ActionRefSchema = z.union([StaticActionSchema, id]);

export const RectSchema = z.tuple([z.number(), z.number(), z.number(), z.number()]);

const base = {
  id,
  slot: z.string().min(1).max(64).optional(),
  rect: RectSchema.optional(),
  a11y: z.object({ label: z.string().optional(), role: z.string().optional() }).optional(),
  on: z.record(z.string(), ActionRefSchema).optional(),
};
const valueBase = {
  ...base,
  label: z.string(),
  bind: path.optional(),
  commit: z.enum(["submit", "blur", "change"]).optional(),
};
const ListItemSchema = z.object({ id: z.string(), label: z.string(), meta: z.string().optional() });
const OptionSchema = z.object({ value: z.string(), label: z.string() });

export const ComponentSchema = z.discriminatedUnion("kind", [
  z.object({ ...base, kind: z.literal("text"), value: z.string().optional(), bind: path.optional(),
    variant: z.enum(["title", "subtitle", "body", "caption", "number"]).optional() }),
  z.object({ ...base, kind: z.literal("image"), src: z.string().optional(), bind: path.optional(), alt: z.string().optional() }),
  z.object({ ...base, kind: z.literal("media"), src: z.string().optional(), bind: path.optional(),
    media: z.enum(["video", "audio"]).optional() }),
  z.object({ ...base, kind: z.literal("button"), label: z.string(), emphasis: z.enum(["primary", "secondary"]).optional() }),
  z.object({ ...base, kind: z.literal("link"), label: z.string() }),
  z.object({ ...valueBase, kind: z.literal("input"), type: z.enum(["text", "secret", "email", "number", "search"]).optional(),
    placeholder: z.string().optional() }),
  z.object({ ...valueBase, kind: z.literal("textarea"), placeholder: z.string().optional() }),
  z.object({ ...valueBase, kind: z.literal("select"), options: z.union([z.array(OptionSchema), z.object({ bind: path })]) }),
  z.object({ ...valueBase, kind: z.literal("toggle") }),
  z.object({ ...valueBase, kind: z.literal("slider"), min: z.number().optional(), max: z.number().optional(),
    step: z.number().optional() }),
  z.object({ ...valueBase, kind: z.literal("date") }),
  z.object({ ...base, kind: z.literal("list"), items: z.array(ListItemSchema).optional(), bind: path.optional(),
    label: z.string().optional() }),
]);
export type ComponentSpec = z.infer<typeof ComponentSchema>;

export const FrameSchema = z.object({
  id,
  title: z.string().optional(),
  layout: z.enum(ARCHETYPES).optional(),
  /** Static scene text, or `{ dynamic: true }` when the scene is a function of flavour. */
  scene: z.union([z.string(), z.object({ dynamic: z.literal(true) })]).optional(),
  flavour: z.boolean().optional(),
  enter: z.boolean().optional(),
  cut: z.enum(["crossfade", "generated", "none"]).optional(),
  components: z.array(ComponentSchema),
  on: z.record(z.string(), z.object({ outcomes: z.array(ActionSchema).optional() })).optional(),
});
export type FrameSpec = z.infer<typeof FrameSchema>;

export const TapeSchema = z.object({
  id,
  title: z.string().optional(),
  style: z.string(),
  entry: id,
  frames: z.array(FrameSchema).min(1),
});
export type TapeSpec = z.infer<typeof TapeSchema>;

const hex = z.string().regex(/^#[0-9a-fA-F]{6}$/);
export const StylePackSchema = z.object({
  id,
  seed: z.number().int().nonnegative(),
  palette: z.object({ bg: hex, fg: hex, accent: hex, muted: hex }),
  fonts: z.object({ display: z.string(), body: z.string() }),
  prompt: z.object({ prefix: z.string(), suffix: z.string(), negative: z.string().optional() }),
  references: z.array(z.string()),
  lora: z.string().nullable(),
});

export const AppSchema = z.object({
  v: z.literal(1),
  entry: id,
  tapes: z.array(TapeSchema).min(1),
  styles: z.array(StylePackSchema),
});
export type AppSpec = z.infer<typeof AppSchema>;
