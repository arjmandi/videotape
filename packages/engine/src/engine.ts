// The engine (spec §4, §5.2, §9, §10): reels, the VTP message loop, handlers,
// and the render pipeline resolve → layout → plan → generate → deliver.
// Transport-free: a Connection takes raw text in and calls `send` with messages
// out, so tests drive it directly and the server wraps it in a WebSocket.

import { randomBytes } from "node:crypto";
import {
  type Action, type App, type ClientMessage, type Content, type Data, type DataPatch, type Edge,
  type EventMessage, type Flavour, type Frame, type Head, type HelloMessage, type ReelInfo, type RenderMessage,
  type SceneRenderer, type ServerMessage, type Services, type StylePack, type Tape, type ViewportClass, type Wireframe,
  CANVAS, ClientMessageSchema, KIND_EVENTS, ServerMessageSchema, VALUE_KINDS, applyPatch, check, decode, largestFreeArea, layout, sceneSvg, setPath,
  styleById, tapeEntry, viewportClass,
} from "@videotape/core";
import { flatRenderer } from "@videotape/renderer-flat";
import { type Cache, MemoryCache } from "./cache";
import { type Budgets, DEFAULT_BUDGETS, type VideotapeConfig } from "./config";
import { buildContent, diffContent, validValue } from "./content";
import { type ScenePlan, RendererHost, type SceneResult, type Validator } from "./host";
import { frameSpecHash } from "./keys";
import { type Logger, consoleLogger } from "./log";
import { composePrompt, sceneText } from "./prompt";

export interface EngineOptions {
  cache?: Cache;
  logger?: Logger;
  /** Scene renderers in preference order; flat is appended if missing. Overrides config.renderers. */
  renderers?: SceneRenderer[];
  validator?: Validator;
  debug?: boolean;
  budgets?: Partial<Budgets>;
  /** How long a disconnected reel can be resumed. */
  resumeTtlMs?: number;
  /** False: serve only scenes already in the cache, so serving never spends on generation. */
  generate?: boolean;
  /**
   * Freedom given to generators when a frame's scene drawing has almost no structure
   * (panels and media frames under 2 % of the canvas). Image-to-image over a bare gradient
   * otherwise returns the gradient. Default 0.95; `false` turns it off.
   */
  emptyFreedom?: number | false;
}

/** Share of the canvas the scene drawing gives a generator to build on: panels and media frames. */
export function drawingStructure(wf: Wireframe): number {
  return wf.regions
    .filter((r) => r.kind === "panel" || r.kind === "image" || r.kind === "media")
    .reduce((sum, r) => sum + r.rect[2] * r.rect[3], 0);
}

/** Below this structure, a drawing counts as empty. */
export const EMPTY_DRAWING = 0.02;

interface Reel {
  id: string;
  token: string;
  head: Head;
  history: Head[];
  data: Data;
  viewport: { w: number; h: number; dpr: number };
  cls: ViewportClass;
  outSeq: number;
  /** Seq of the last render sent; events must name it. */
  renderSeq: number;
  content: Content[];
  sceneKey: string;
  connection?: Connection;
  detachedAt?: number;
  /** Debug-only seed offsets per frame, bumped by `reroll`. */
  rerolls: Map<string, number>;
}

interface Located {
  tape: Tape;
  frame: Frame;
}

export class Engine {
  readonly app: App;
  readonly services: Services;
  readonly host: RendererHost;
  readonly cache: Cache;
  readonly log: Logger;
  readonly debug: boolean;
  readonly budgets: Budgets;
  private readonly tapes = new Map<string, Tape>();
  private readonly reels = new Map<string, Reel>();
  private readonly wireframes = new Map<string, Wireframe>();
  private readonly resumeTtlMs: number;
  private readonly emptyFreedom: number | false;

  constructor(config: VideotapeConfig, opts: EngineOptions = {}) {
    const errors = check(config.app).filter((d) => d.level === "error");
    if (errors.length) {
      throw new Error(`the app does not pass check:\n${errors.map((d) => `  ${d.code} ${d.at ?? ""} ${d.message}`).join("\n")}`);
    }
    this.app = config.app;
    this.services = config.services ?? ({} as Services);
    this.cache = opts.cache ?? new MemoryCache();
    this.log = opts.logger ?? consoleLogger();
    this.debug = opts.debug ?? config.debug ?? false;
    this.budgets = { ...DEFAULT_BUDGETS, ...config.budgets, ...opts.budgets };
    this.resumeTtlMs = opts.resumeTtlMs ?? 10 * 60_000;
    this.emptyFreedom = opts.emptyFreedom ?? 0.95;
    for (const t of config.app.tapes) this.tapes.set(t.id, t);

    const renderers = opts.renderers ?? (config.renderers ?? []).map((r) => {
      if (typeof r !== "string") return r;
      if (r === "flat") return flatRenderer();
      throw new Error(`renderer "${r}" must be resolved to an instance before it reaches the engine`);
    });
    if (!renderers.some((r) => r.id === "flat")) renderers.push(flatRenderer());
    this.host = new RendererHost(renderers, {
      cache: this.cache, logger: this.log, ...(opts.validator ? { validator: opts.validator } : {}),
      ...(opts.generate === false ? { generate: false } : {}),
    });
  }

  /** Opens a connection. `send` receives every message for this client. */
  connect(send: (m: ServerMessage) => void): Connection {
    this.sweep();
    return new Connection(this, send);
  }

  // ── lookups ───────────────────────────────────────────────────────────────

  locate(head: Head): Located {
    const tape = this.tapes.get(head.tape);
    const frame = tape?.frames.find((f) => f.id === head.frame);
    if (!tape || !frame) throw new Error(`no frame ${head.tape}/${head.frame}`);
    return { tape, frame };
  }

  entryHead(tapeId: string): Head | undefined {
    const t = this.tapes.get(tapeId);
    const f = t && tapeEntry(t);
    return t && f ? { tape: t.id, frame: f } : undefined;
  }

  styleOf(tape: Tape): StylePack {
    return styleById(tape.style ?? "dusk", this.app.styles)!;
  }

  wireframe(frame: Frame, tape: Tape, cls: ViewportClass): Wireframe {
    const k = `${tape.id}/${frame.id}/${cls}`;
    let wf = this.wireframes.get(k);
    if (!wf) {
      wf = layout(frame, cls, this.styleOf(tape));
      this.wireframes.set(k, wf);
    }
    return wf;
  }

  flavour(frame: Frame, data: Data): Flavour {
    if (!frame.flavour) return {};
    try {
      return frame.flavour(data);
    } catch (e) {
      this.log.warn("flavour threw; using none", { frame: frame.id, error: e instanceof Error ? e.message : String(e) });
      return {};
    }
  }

  plan(head: Head, data: Data, cls: ViewportClass, seedOffset = 0): ScenePlan {
    const { tape, frame } = this.locate(head);
    const style = this.styleOf(tape);
    const wf = this.wireframe(frame, tape, cls);
    const flavour = this.flavour(frame, data);
    // A drawing with nothing to build on gets extra freedom, and then needs telling where the
    // subject goes, or the model centres it behind the headline (03-landscape §2.4).
    const freedom = this.emptyFreedom !== false && drawingStructure(wf) < EMPTY_DRAWING ? this.emptyFreedom : undefined;
    const focus = freedom !== undefined ? largestFreeArea(wf) : undefined;
    return {
      node: `${head.tape}/${head.frame}`,
      frameHash: frameSpecHash(frame),
      viewportClass: cls,
      style,
      seed: style.seed + seedOffset,
      flavour,
      wireframe: wf,
      prompt: composePrompt(style, sceneText(frame, flavour), wf, focus),
      condition: sceneSvg(wf.regions, wf.canvas, style, focus ? { focus } : {}),
      ...(freedom !== undefined ? { freedom } : {}),
    };
  }

  // ── reels ─────────────────────────────────────────────────────────────────

  createReel(hello: HelloMessage): Reel {
    const head = this.entryHead(this.app.entry)!;
    const reel: Reel = {
      id: "s_" + randomBytes(6).toString("hex"),
      token: randomBytes(24).toString("base64url"),
      head,
      history: [],
      data: {},
      viewport: hello.viewport,
      cls: viewportClass(hello.viewport.w),
      outSeq: 0,
      renderSeq: 0,
      content: [],
      sceneKey: "",
      rerolls: new Map(),
    };
    this.reels.set(reel.token, reel);
    return reel;
  }

  resumeReel(token: string | undefined): Reel | undefined {
    if (!token) return undefined;
    const r = this.reels.get(token);
    if (!r || (r.detachedAt && Date.now() - r.detachedAt > this.resumeTtlMs)) return undefined;
    return r;
  }

  /** Number of live reels, for tests and the health endpoint. */
  get reelCount(): number {
    return this.reels.size;
  }

  private sweep(): void {
    const now = Date.now();
    for (const [token, r] of this.reels) {
      if (r.detachedAt && now - r.detachedAt > this.resumeTtlMs) this.reels.delete(token);
    }
  }

  reelInfo(r: Reel): ReelInfo {
    return { session: r.id, head: { ...r.head }, history: r.history.map((h) => ({ ...h })), viewportClass: r.cls };
  }
}

/** One client socket. Messages are handled one at a time, in order. */
export class Connection {
  private reel: Reel | undefined;
  private inSeq = 0;
  private queue: Promise<void> = Promise.resolve();
  private closed = false;

  constructor(private readonly engine: Engine, private readonly sendRaw: (m: ServerMessage) => void) {}

  get session(): string | undefined {
    return this.reel?.id;
  }

  /** Accepts one raw text frame. Resolves when it (and everything before it) is handled. */
  receive(raw: string): Promise<void> {
    const decoded = decode(ClientMessageSchema, raw);
    if (!decoded.ok) {
      this.engine.log.warn("dropped malformed message", { session: this.reel?.id, reason: decoded.reason.slice(0, 200) });
      this.send({ t: "error", code: "bad_message", message: "message rejected", recoverable: true });
      return this.queue;
    }
    const msg = decoded.msg;
    if (msg.t === "ping") {
      this.send({ t: "pong" });
      return this.queue;
    }
    this.queue = this.queue.then(() => this.handle(msg)).catch((e: unknown) => {
      this.engine.log.error("message handling failed", { session: this.reel?.id, error: e instanceof Error ? e.stack ?? e.message : String(e) });
      this.send({ t: "error", code: "internal", message: "the engine could not handle that", recoverable: true });
    });
    return this.queue;
  }

  close(): void {
    this.closed = true;
    if (this.reel?.connection === this) {
      this.reel.connection = undefined;
      this.reel.detachedAt = Date.now();
    }
  }

  private send(m: ServerMessage): void {
    if (this.closed) return;
    const check = ServerMessageSchema.safeParse(m);
    if (!check.success) {
      this.engine.log.error("refusing to send an invalid message", { t: m.t, reason: check.error.issues[0]?.message });
      return;
    }
    this.sendRaw(m);
  }

  private async handle(msg: Exclude<ClientMessage, { t: "ping" }>): Promise<void> {
    if (msg.t === "hello") return this.hello(msg);
    const reel = this.reel;
    if (!reel) {
      this.send({ t: "error", code: "no_session", message: "send hello first", recoverable: true });
      return;
    }
    switch (msg.t) {
      case "event": return this.event(reel, msg);
      case "resize": {
        reel.viewport = msg.viewport;
        const cls = viewportClass(msg.viewport.w);
        if (cls !== reel.cls) {
          reel.cls = cls;
          await this.render(reel, { budgetMs: this.engine.budgets.transitionMs });
        }
        return;
      }
      case "reroll": {
        if (!this.engine.debug) {
          this.engine.log.warn("reroll refused outside debug", { session: reel.id });
          return;
        }
        const node = `${reel.head.tape}/${reel.head.frame}`;
        reel.rerolls.set(node, (reel.rerolls.get(node) ?? 0) + 1);
        await this.render(reel, { budgetMs: this.engine.budgets.transitionMs });
        return;
      }
    }
  }

  private async hello(msg: HelloMessage): Promise<void> {
    const e = this.engine;
    this.inSeq = 0;
    let reel = e.resumeReel(msg.resume);
    const resumed = !!reel;
    if (reel) {
      reel.connection?.close();
      reel.viewport = msg.viewport;
      reel.cls = viewportClass(msg.viewport.w);
      delete reel.detachedAt;
    } else {
      reel = e.createReel(msg);
    }
    reel.connection = this;
    this.reel = reel;
    const { tape } = e.locate(reel.head);
    const style = e.styleOf(tape);
    this.send({
      t: "welcome",
      session: reel.id,
      token: reel.token,
      viewportClass: reel.cls,
      canvas: CANVAS[reel.cls],
      style: { id: style.id, palette: style.palette, fonts: style.fonts },
      ...(e.debug ? { debug: true } : {}),
    });
    e.log.info(resumed ? "session resumed" : "session started", { session: reel.id, viewport: `${msg.viewport.w}x${msg.viewport.h}`, cls: reel.cls });
    if (!resumed) await this.enter(reel);
    await this.render(reel, { budgetMs: e.budgets.firstRenderMs });
  }

  // ── events ────────────────────────────────────────────────────────────────

  private drop(reel: Reel, reason: string, msg: EventMessage): void {
    this.engine.log.warn(`dropped event: ${reason}`, { session: reel.id, component: msg.component, type: msg.type, seq: msg.seq });
  }

  private async event(reel: Reel, msg: EventMessage): Promise<void> {
    if (msg.seq <= this.inSeq) return this.drop(reel, "replayed seq", msg);
    this.inSeq = msg.seq;
    if (msg.render !== reel.renderSeq) return this.drop(reel, "stale render", msg);

    const { tape, frame } = this.engine.locate(reel.head);
    const c = frame.components.find((x) => x.id === msg.component);
    if (!c) return this.drop(reel, "unknown component", msg);
    if (!KIND_EVENTS[c.kind].includes(msg.type)) return this.drop(reel, "event not emitted by this kind", msg);
    if (msg.value !== undefined && !validValue(c, msg.value, reel.data)) return this.drop(reel, "invalid value", msg);
    if (c.kind === "list" && msg.value === undefined) return this.drop(reel, "select without an item", msg);

    // Committed form values travel with the event; every key must be a value component on this frame.
    const values: Record<string, unknown> = {};
    for (const [id, v] of Object.entries(msg.values ?? {})) {
      const vc = frame.components.find((x) => x.id === id);
      if (!vc || !VALUE_KINDS.includes(vc.kind)) return this.drop(reel, `values names a non-value component`, msg);
      if (!validValue(vc, v, reel.data)) return this.drop(reel, "invalid value in values", msg);
      values[id] = v;
    }
    if (msg.value !== undefined) {
      if (c.kind === "list") values.item = msg.value;
      else values[c.id] = msg.value;
    }

    // Bound values are committed to the store; secrets never are (check forbids binding them).
    const before = reel.content;
    for (const [id, v] of Object.entries(values)) {
      const vc = frame.components.find((x) => x.id === id);
      if (vc && VALUE_KINDS.includes(vc.kind) && "bind" in vc && vc.bind && !(vc.kind === "input" && vc.type === "secret")) {
        reel.data = setPath(reel.data, vc.bind, v);
      }
    }

    const ref = c.on?.[msg.type];
    if (ref === undefined) {
      // Only a bound value component may send an event its frame does not handle: it is a commit.
      if (VALUE_KINDS.includes(c.kind) && "bind" in c && c.bind) return this.stay(reel, before, undefined);
      return this.drop(reel, "not handled by this frame", msg);
    }

    let action: Action;
    if (typeof ref === "string") {
      const h = frame.on?.[ref];
      if (!h) return this.drop(reel, "handler missing", msg);
      try {
        action = await h.fn({
          values,
          ...(msg.value !== undefined ? { value: msg.value } : {}),
          event: { component: c.id, type: msg.type },
          data: reel.data,
          services: this.engine.services,
          reel: this.engine.reelInfo(reel),
        });
      } catch (e) {
        this.engine.log.error("handler threw", { session: reel.id, handler: ref, error: e instanceof Error ? e.message : String(e) });
        this.send({ t: "error", code: "handler_failed", message: "Something went wrong. Please try again.", recoverable: true });
        return this.stay(reel, before, undefined);
      }
      if (!h.outcomes?.some((o) => sameOutcome(o, action))) {
        this.engine.log.warn("handler returned an undeclared outcome", { session: reel.id, handler: ref, type: action.type });
      }
    } else {
      action = ref;
    }
    return this.apply(reel, tape, action, before);
  }

  private async apply(reel: Reel, tape: Tape, action: Action, before: Content[]): Promise<void> {
    const e = this.engine;
    switch (action.type) {
      case "stay":
        return this.stay(reel, before, action.patch);
      case "goto": {
        if (!tape.frames.some((f) => f.id === action.frame)) return this.badTarget(reel, before, `goto ${action.frame}`);
        reel.head = { tape: tape.id, frame: action.frame };
        break;
      }
      case "jump": {
        const head = e.entryHead(action.tape);
        if (!head) return this.badTarget(reel, before, `jump ${action.tape}`);
        reel.history.push(reel.head);
        reel.head = head;
        reel.data = applyPatch(reel.data, action.data);
        break;
      }
      case "back": {
        const prev = reel.history.pop();
        if (!prev) return this.stay(reel, before, undefined);
        reel.head = prev;
        break;
      }
    }
    await this.enter(reel);
    await this.render(reel, { budgetMs: e.budgets.transitionMs, cut: true });
  }

  private badTarget(reel: Reel, before: Content[], what: string): Promise<void> {
    this.engine.log.error("action names an unknown target", { session: reel.id, target: what });
    this.send({ t: "error", code: "bad_target", message: "That way is closed.", recoverable: true });
    return this.stay(reel, before, undefined);
  }

  /** Applies a patch and sends only what changed. Always replies, so the player re-enables input. */
  private async stay(reel: Reel, before: Content[], patch: DataPatch | undefined): Promise<void> {
    reel.data = applyPatch(reel.data, patch);
    const { tape, frame } = this.engine.locate(reel.head);
    const content = buildContent(frame, this.engine.wireframe(frame, tape, reel.cls), reel.data);
    reel.content = content;
    this.send({ t: "patch", seq: ++reel.outSeq, render: reel.renderSeq, content: diffContent(before, content) });
  }

  private async enter(reel: Reel): Promise<void> {
    const { frame } = this.engine.locate(reel.head);
    if (!frame.enter) return;
    try {
      const patch = await frame.enter({ data: reel.data, services: this.engine.services, reel: this.engine.reelInfo(reel) });
      if (patch) reel.data = applyPatch(reel.data, patch);
    } catch (e) {
      this.engine.log.error("enter hook threw", { session: reel.id, frame: frame.id, error: e instanceof Error ? e.message : String(e) });
    }
  }

  // ── rendering ─────────────────────────────────────────────────────────────

  private async render(reel: Reel, opts: { budgetMs: number; cut?: boolean }): Promise<void> {
    const e = this.engine;
    const started = performance.now();
    const head = { ...reel.head };
    const { tape, frame } = e.locate(head);
    const node = `${head.tape}/${head.frame}`;
    const plan = e.plan(head, reel.data, reel.cls, e.debug ? reel.rerolls.get(node) ?? 0 : 0);
    const scene = await e.host.scene(plan, opts.budgetMs);
    const content = buildContent(frame, plan.wireframe, reel.data);
    const edges = this.edges(reel, tape, frame);

    if (opts.cut && reel.sceneKey && frame.cut !== "none") {
      this.send({ t: "cut", seq: ++reel.outSeq, from: reel.sceneKey, to: scene.key, durationMs: e.budgets.crossfadeMs, kind: "crossfade" });
    }
    const seq = ++reel.outSeq;
    const msg: RenderMessage = {
      t: "render",
      seq,
      head,
      canvas: plan.wireframe.canvas,
      key: scene.key,
      layers: [scene.layer],
      regions: plan.wireframe.regions.map((r) => ({ id: r.id, kind: r.kind, rect: r.rect, mask: r.mask, z: r.z })),
      content,
      edges,
      a11y: { title: frame.title ?? tape.title ?? frame.id },
      fallback: scene.fallback,
    };
    if (e.debug) msg.debug = debugInfo(scene, performance.now() - started, e.host.stats);
    reel.renderSeq = seq;
    reel.content = content;
    reel.sceneKey = scene.key;
    this.send(msg);

    if (scene.pending) void this.patchWhenReady(reel, seq, scene.pending);
    void this.prefetch(reel, edges);
  }

  /** Swaps a fallback scene for the generated one, if the player is still on that render. */
  private async patchWhenReady(reel: Reel, seq: number, pending: Promise<SceneResult | undefined>): Promise<void> {
    const r = await pending;
    if (!r || reel.renderSeq !== seq || reel.connection !== this) return;
    reel.sceneKey = r.key;
    this.send({ t: "patch", seq: ++reel.outSeq, render: seq, layers: [r.layer], key: r.key, fallback: false });
  }

  private edges(reel: Reel, tape: Tape, frame: Frame): Edge[] {
    const out: Edge[] = [];
    const target = (a: Action): Head | undefined => {
      if (a.type === "goto") return { tape: tape.id, frame: a.frame };
      if (a.type === "jump") return this.engine.entryHead(a.tape);
      if (a.type === "back") return reel.history[reel.history.length - 1];
      return undefined;
    };
    for (const c of frame.components) {
      for (const [event, ref] of Object.entries(c.on ?? {})) {
        if (ref === undefined) continue;
        const actions = typeof ref === "string" ? frame.on?.[ref]?.outcomes ?? [] : [ref];
        for (const a of actions) {
          const to = target(a);
          out.push({ component: c.id, event, kind: a.type, ...(to ? { to } : {}), ...(typeof ref === "string" ? { handler: ref } : {}) });
        }
      }
    }
    return out;
  }

  /** Warms the scene of every outgoing edge's target and tells the player where they are (spec §7.5). */
  private async prefetch(reel: Reel, edges: Edge[]): Promise<void> {
    const e = this.engine;
    const seen = new Set<string>();
    const assets: Array<{ url: string; kind: "scene"; forEdge: string }> = [];
    for (const edge of edges) {
      if (!edge.to || edge.kind === "stay") continue;
      const node = `${edge.to.tape}/${edge.to.frame}`;
      if (seen.has(node)) continue;
      seen.add(node);
      try {
        const scene = await e.host.scene(e.plan(edge.to, reel.data, reel.cls), 0, { quiet: true });
        assets.push({ url: scene.layer.url, kind: "scene", forEdge: `${edge.component}:${edge.event}` });
      } catch (err) {
        e.log.warn("prefetch failed", { session: reel.id, node, error: err instanceof Error ? err.message : String(err) });
      }
    }
    if (assets.length && reel.connection === this) this.send({ t: "prefetch", assets });
  }
}

function sameOutcome(declared: Action, got: Action): boolean {
  if (declared.type !== got.type) return false;
  if (declared.type === "jump" && got.type === "jump") return declared.tape === got.tape;
  if (declared.type === "goto" && got.type === "goto") return declared.frame === got.frame;
  return true;
}

function debugInfo(scene: SceneResult, ms: number, stats: RendererHost["stats"]): Record<string, unknown> {
  return {
    renderer: scene.renderer,
    cache: scene.cache,
    ms: Math.round(ms),
    ...(scene.rerolls !== undefined ? { rerolls: scene.rerolls } : {}),
    ...(scene.patched?.length ? { patched: scene.patched } : {}),
    stats: { ...stats },
  };
}
