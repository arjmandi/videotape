// `videotape check` (spec §5.6): static validation of an app.

import { buildGraph, closedCycles, hasExit, reachable } from "./graph";
import { emphasisOf, layout, resolveArchetype } from "./layout";
import { ACTION_KINDS, type App, KIND_EVENTS, VALUE_KINDS } from "./model";
import { traceReads } from "./paths";
import { type ActionSpec, AppSchema, type AppSpec, type FrameSpec, type TapeSpec } from "./schema";
import { toSpec } from "./serialize";
import { styleById } from "./style";
import { VIEWPORT_CLASSES } from "./viewport";

export interface Diagnostic {
  level: "error" | "warning";
  code: string;
  message: string;
  /** `tape`, `tape/frame`, or `tape/frame#component`. */
  at?: string;
}

export function check(app: App): Diagnostic[] {
  const out: Diagnostic[] = [];
  const err = (code: string, message: string, at?: string) => out.push({ level: "error", code, message, ...(at ? { at } : {}) });
  const warn = (code: string, message: string, at?: string) => out.push({ level: "warning", code, message, ...(at ? { at } : {}) });

  const parsed = AppSchema.safeParse(toSpec(app));
  if (!parsed.success) {
    for (const issue of parsed.error.issues) err("schema", issue.message, issue.path.join("."));
    return out;
  }
  const spec = parsed.data;

  dupes(spec.tapes.map((t) => t.id)).forEach((id) => err("duplicate-id", `tape "${id}" is defined more than once`, id));
  if (!spec.tapes.some((t) => t.id === spec.entry)) err("unknown-tape", `the app's entry tape "${spec.entry}" does not exist`);

  // Paths that inputs write to, for the scene lint.
  const inputPaths = spec.tapes.flatMap((t) => t.frames.flatMap((f) =>
    f.components.filter((c) => VALUE_KINDS.includes(c.kind) && "bind" in c && c.bind).map((c) => (c as { bind: string }).bind)));

  for (const t of spec.tapes) {
    dupes(t.frames.map((f) => f.id)).forEach((id) => err("duplicate-id", `frame "${id}" is defined more than once`, `${t.id}/${id}`));
    if (!t.frames.some((f) => f.id === t.entry)) err("unknown-frame", `entry frame "${t.entry}" does not exist`, t.id);
    const style = styleById(t.style, spec.styles);
    if (!style) err("unknown-style", `style "${t.style}" is not defined`, t.id);
    for (const f of t.frames) {
      checkFrame(spec, t, f, err, warn);
      if (style) {
        const seen = new Set<string>();
        for (const cls of VIEWPORT_CLASSES) {
          for (const d of layout(f, cls, style).diagnostics) {
            const at = `${t.id}/${f.id}${d.component ? `#${d.component}` : ""}`;
            const key = d.code + at;
            if (d.code === "overflow") warn("overflow", `${d.message}`, at);
            else if (!seen.has(key)) err(d.code, d.message, at);
            seen.add(key);
          }
        }
      }
    }
  }

  // Scene functions must not read what users type (spec §5.5).
  for (const t of app.tapes) {
    for (const f of t.frames) {
      if (!f.flavour) continue;
      for (const read of traceReads(f.flavour)) {
        const hit = inputPaths.find((p) => p === read || read.startsWith(p + ".") || p.startsWith(read + "."));
        if (hit) warn("scene-reads-input", `flavour reads "${read}", which an input writes ("${hit}")`, `${t.id}/${f.id}`);
      }
    }
  }

  const g = buildGraph(spec);
  const live = reachable(g);
  for (const n of g.nodes) {
    if (!live.has(n)) warn("unreachable-frame", `frame "${n}" cannot be reached from the entry`, n);
    else if (!hasExit(g, n)) warn("no-exit", `frame "${n}" has no way out`, n);
  }
  for (const scc of closedCycles(g)) warn("closed-cycle", `frames ${scc.join(", ")} form a cycle with no exit`, scc[0]);

  return out;
}

type Report = (code: string, message: string, at?: string) => void;

function checkFrame(spec: AppSpec, t: TapeSpec, f: FrameSpec, err: Report, warn: Report): void {
  const at = (c?: string) => `${t.id}/${f.id}${c ? `#${c}` : ""}`;
  dupes(f.components.map((c) => c.id)).forEach((id) => err("duplicate-id", `component "${id}" is defined more than once`, at(id)));

  const checkTarget = (a: ActionSpec, where: string) => {
    if (a.type === "goto" && !t.frames.some((x) => x.id === a.frame)) err("unknown-frame", `goto("${a.frame}"): no such frame in tape "${t.id}"`, where);
    if (a.type === "jump" && !spec.tapes.some((x) => x.id === a.tape)) err("unknown-tape", `jump("${a.tape}"): no such tape`, where);
  };

  const used = new Set<string>();
  let primaries = 0;
  const archetype = resolveArchetype(f);
  for (const c of f.components) {
    const on = Object.entries(c.on ?? {});
    for (const [event, ref] of on) {
      if (!KIND_EVENTS[c.kind].includes(event)) {
        err("bad-event", `a ${c.kind} does not emit "${event}"`, at(c.id));
        continue;
      }
      if (typeof ref === "string") {
        used.add(ref);
        if (!f.on?.[ref]) err("unknown-handler", `handler "${ref}" is not defined on this frame`, at(c.id));
      } else {
        checkTarget(ref, at(c.id));
      }
    }
    if (ACTION_KINDS.includes(c.kind) && on.length === 0) err("no-action", `this ${c.kind} has no action and no handler`, at(c.id));
    if (c.kind === "input" && c.type === "secret" && c.bind) err("secret-bind", `a secret input cannot be bound to "${c.bind}"`, at(c.id));
    if (c.kind === "button" && emphasisOf(c, archetype === "blank" ? undefined : c.slot) === "primary") primaries++;
  }
  if (primaries > 1) warn("multiple-primary", `${primaries} primary buttons on one frame`, at());

  for (const [name, h] of Object.entries(f.on ?? {})) {
    if (!h.outcomes) warn("handler-without-outcomes", `handler "${name}" declares no outcomes; its edges are unknown`, at());
    for (const o of h.outcomes ?? []) checkTarget(o, at());
    if (!used.has(name)) warn("unused-handler", `handler "${name}" is not used by any component`, at());
  }
  const values = f.components.filter((c) => VALUE_KINDS.includes(c.kind));
  if (values.length && !values.some((c) => "bind" in c && c.bind) && Object.keys(f.on ?? {}).length === 0) {
    warn("unused-values", "this frame collects values but has no handler to receive them", at());
  }
}

function dupes(ids: string[]): string[] {
  const seen = new Set<string>();
  const out = new Set<string>();
  for (const id of ids) (seen.has(id) ? out : seen).add(id);
  return [...out];
}
