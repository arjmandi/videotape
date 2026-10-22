// The player (spec §8): connect → hello → welcome → render → mount content →
// prefetch → … → event → cut → render. It shows what it is told, sends what the
// user does, and decides nothing about the app.

import {
  CANVAS, type CutMessage, type PatchMessage, type PrefetchMessage, type RenderMessage, type ServerMessage, type Size,
  type ViewportClass, type WelcomeMessage, stageFit, viewportClass,
} from "@videotape/core";
import { Hud } from "./hud";
import { Link } from "./link";
import { type BuildState, type NodeHost, type VNode, type Value, createNode } from "./nodes";

export interface PlayerOptions {
  url: string;
  debug: boolean;
}

const TOKEN_KEY = "videotape.token";
/** A transition that takes longer than this re-enables input and says so (spec §8). */
const BUSY_TIMEOUT_MS = 2000;
const DECODE_WAIT_MS = 250;

function storage(): Storage | undefined {
  try {
    return window.sessionStorage;
  } catch {
    return undefined;
  }
}

export class Player implements NodeHost {
  private readonly link: Link;
  private readonly stage: HTMLDivElement;
  private readonly backdrop: HTMLImageElement;
  private readonly scenes: [HTMLImageElement, HTMLImageElement];
  private readonly content: HTMLElement;
  private readonly badge: HTMLDivElement;
  private readonly toastEl: HTMLDivElement;
  private readonly hud: Hud;
  private front = 0;
  private canvas: Size = CANVAS.desktop;
  private cls: ViewportClass = "desktop";
  private token: string | undefined;
  private seq = 0;
  private current: RenderMessage | undefined;
  private latestRender = 0;
  private nodes = new Map<string, VNode>();
  private pendingCut: CutMessage | undefined;
  private busy = false;
  private busyTimer: ReturnType<typeof setTimeout> | undefined;
  private toastTimer: ReturnType<typeof setTimeout> | undefined;
  private pressedAt: number | undefined;
  private lastTransitionMs: number | undefined;
  private readonly prefetchState = new Map<string, string>();
  private readonly warm = new Set<HTMLImageElement>();
  private rendered = 0;

  constructor(private readonly root: HTMLElement, private readonly opts: PlayerOptions) {
    this.token = storage()?.getItem(TOKEN_KEY) ?? undefined;
    this.backdrop = this.el("img", "vt-backdrop", root);
    this.backdrop.alt = "";
    this.backdrop.setAttribute("aria-hidden", "true");
    this.stage = this.el("div", "vt-stage", root);
    this.scenes = [this.el("img", "vt-scene", this.stage), this.el("img", "vt-scene is-back", this.stage)];
    for (const s of this.scenes) {
      s.alt = "";
      s.setAttribute("aria-hidden", "true");
    }
    this.content = this.el("main", "vt-content", this.stage);
    this.content.setAttribute("aria-busy", "true");
    this.hud = new Hud(this.stage, root);
    this.hud.enabled = opts.debug;
    this.badge = this.el("div", "vt-badge", root);
    this.badge.setAttribute("role", "status");
    this.badge.hidden = true;
    this.toastEl = this.el("div", "vt-toast", root);
    this.toastEl.setAttribute("role", "alert");
    this.toastEl.hidden = true;
    this.link = new Link(opts.url, {
      open: () => this.hello(),
      message: (m) => this.receive(m),
      down: () => this.offline(),
    });
  }

  start(): void {
    this.fit();
    let t: ReturnType<typeof setTimeout> | undefined;
    window.addEventListener("resize", () => {
      clearTimeout(t);
      t = setTimeout(() => this.resized(), 150);
    });
    window.addEventListener("keydown", (e) => this.key(e));
    this.link.connect();
  }

  private el<K extends keyof HTMLElementTagNameMap>(tag: K, className: string, parent: HTMLElement): HTMLElementTagNameMap[K] {
    const el = document.createElement(tag);
    el.className = className;
    parent.append(el);
    return el;
  }

  private set state(s: "connecting" | "ready" | "busy" | "offline") {
    this.root.dataset.vtState = s;
  }

  // ── connection ────────────────────────────────────────────────────────────

  private viewport() {
    return { w: Math.max(1, window.innerWidth), h: Math.max(1, window.innerHeight), dpr: Math.min(8, window.devicePixelRatio || 1) };
  }

  private hello(): void {
    this.seq = 0;
    this.link.send({
      t: "hello", v: 1, viewport: this.viewport(),
      caps: { video: ["webm", "mp4"], webrtc: typeof RTCPeerConnection !== "undefined" },
      ...(this.token ? { resume: this.token } : {}),
    });
  }

  private offline(): void {
    this.state = "offline";
    this.content.classList.add("is-busy");
    this.badge.textContent = "Reconnecting…";
    this.badge.hidden = false;
  }

  private receive(m: ServerMessage): void {
    switch (m.t) {
      case "welcome": return this.welcome(m);
      case "render": return void this.render(m);
      case "cut": this.pendingCut = m; return;
      case "patch": return this.patch(m);
      case "prefetch": return this.prefetch(m);
      case "error":
        this.idle();
        this.toast(m.message);
        if (!m.recoverable) this.offline();
        return;
      case "pong": return;
    }
  }

  private welcome(w: WelcomeMessage): void {
    this.token = w.token;
    storage()?.setItem(TOKEN_KEY, w.token);
    this.canvas = w.canvas;
    this.cls = w.viewportClass;
    const s = document.documentElement.style;
    s.setProperty("--vt-bg", w.style.palette.bg);
    s.setProperty("--vt-fg", w.style.palette.fg);
    s.setProperty("--vt-accent", w.style.palette.accent);
    s.setProperty("--vt-muted", w.style.palette.muted);
    s.setProperty("--vt-display", `"${w.style.fonts.display}", "Iowan Old Style", Georgia, serif`);
    s.setProperty("--vt-body", `"${w.style.fonts.body}", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`);
    if (w.debug) this.hud.enabled = true;
    this.badge.hidden = true;
    this.fit();
  }

  // ── stage ─────────────────────────────────────────────────────────────────

  private fit(): void {
    const v = this.viewport();
    const f = stageFit(v, this.canvas);
    const st = this.stage.style;
    st.left = `${f.x}px`;
    st.top = `${f.y}px`;
    st.width = `${f.w}px`;
    st.height = `${f.h}px`;
    this.root.style.setProperty("--s", String(f.scale));
    this.backdrop.hidden = f.covers;
  }

  private resized(): void {
    this.fit();
    const cls = viewportClass(this.viewport().w);
    if (cls !== this.cls) {
      this.cls = cls;
      this.link.send({ t: "resize", viewport: this.viewport() });
    }
  }

  // ── render, patch, prefetch ───────────────────────────────────────────────

  private async render(r: RenderMessage): Promise<void> {
    if (r.seq <= this.latestRender) return;
    this.latestRender = r.seq;
    const cut = this.pendingCut;
    this.pendingCut = undefined;
    const url = r.layers.find((l) => l.kind === "image")?.url;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (url) await this.swapScene(url, reduce ? 0 : cut?.durationMs ?? 0);
    if (r.seq !== this.latestRender) return; // a newer render arrived while this one loaded

    if (r.fallback && this.current?.head && cut) this.toast("Showing a simpler picture while the scene renders");
    this.current = r;
    if (r.canvas && (r.canvas.w !== this.canvas.w || r.canvas.h !== this.canvas.h)) {
      this.canvas = r.canvas;
      this.fit();
    }
    this.mount(r);
    this.idle();
    this.rendered++;
    this.root.dataset.vtHead = `${r.head.tape}/${r.head.frame}`;
    this.root.dataset.vtSeq = String(r.seq);
    this.root.dataset.vtFallback = String(r.fallback);
    this.content.setAttribute("aria-busy", "false");
    document.title = r.a11y.title ? `${r.a11y.title} · videotape` : "videotape";
    if (this.pressedAt !== undefined) {
      this.lastTransitionMs = performance.now() - this.pressedAt;
      this.pressedAt = undefined;
    }
    this.hud.show(r, { ...(this.lastTransitionMs !== undefined ? { transitionMs: this.lastTransitionMs } : {}), prefetch: this.prefetchState });
    // After a move, put focus at the new frame's heading so screen readers announce it.
    if (this.rendered > 1) this.content.querySelector<HTMLElement>("h1")?.focus({ preventScroll: true });
  }

  private async swapScene(url: string, ms: number): Promise<void> {
    const cur = this.scenes[this.front]!;
    if (cur.getAttribute("src") === url) return;
    const next = this.scenes[1 - this.front]!;
    next.style.transitionDuration = "0ms";
    next.classList.add("is-back");
    next.style.zIndex = "1";
    cur.style.zIndex = "0";
    next.src = url;
    // Decoding first avoids a flash, but the content layer never waits long on the picture:
    // background tabs may not decode at all until they are shown.
    await Promise.race([next.decode().catch(() => undefined), new Promise((r) => setTimeout(r, DECODE_WAIT_MS))]);
    void next.offsetWidth;
    next.style.transitionDuration = `${ms}ms`;
    next.classList.remove("is-back");
    this.front = 1 - this.front;
    this.backdrop.src = url;
  }

  private mount(r: RenderMessage): void {
    const state: BuildState = { headingUsed: false };
    this.nodes.clear();
    const els = r.content.map((c) => {
      const n = createNode(c, this, state);
      this.nodes.set(c.id, n);
      return n.el;
    });
    this.content.classList.add("is-entering");
    this.content.replaceChildren(...els);
    requestAnimationFrame(() => this.content.classList.remove("is-entering"));
  }

  private patch(p: PatchMessage): void {
    if (!this.current || p.render !== this.current.seq) return;
    for (const diff of p.content ?? []) this.nodes.get(diff.id)?.update(diff);
    const url = p.layers?.find((l) => l.kind === "image")?.url;
    if (url) {
      void this.swapScene(url, 300);
      this.current = { ...this.current, layers: p.layers!, ...(p.key ? { key: p.key } : {}), fallback: p.fallback ?? false };
      this.root.dataset.vtFallback = String(this.current.fallback);
    }
    this.idle();
  }

  private prefetch(p: PrefetchMessage): void {
    for (const a of p.assets) {
      if (a.kind !== "scene") continue;
      this.prefetchState.set(a.forEdge, "loading");
      const img = new Image();
      this.warm.add(img);
      img.onload = () => this.prefetchState.set(a.forEdge, "ready");
      img.onerror = () => this.prefetchState.set(a.forEdge, "error");
      img.src = a.url;
    }
    if (this.current) this.hud.show(this.current, { prefetch: this.prefetchState });
  }

  // ── input (NodeHost) ──────────────────────────────────────────────────────

  private values(): Record<string, Value> {
    const out: Record<string, Value> = {};
    for (const n of this.nodes.values()) if (n.value && (n.commit ?? "submit") === "submit") out[n.id] = n.value();
    return out;
  }

  private sendEvent(component: string, type: string, extra: { value?: Value; values?: Record<string, Value> }): boolean {
    if (!this.current) return false;
    return this.link.send({ t: "event", seq: ++this.seq, render: this.current.seq, component, type, ...extra });
  }

  press(id: string, el: HTMLElement): void {
    if (this.busy) return;
    const values = this.values();
    if (!this.sendEvent(id, "press", Object.keys(values).length ? { values } : {})) return;
    this.hold(el);
  }

  select(id: string, item: string, el: HTMLElement): void {
    if (this.busy) return;
    if (this.sendEvent(id, "select", { value: item })) this.hold(el);
  }

  change(id: string, value: Value): void {
    this.sendEvent(id, "change", { value });
  }

  commit(id: string, value: Value): void {
    this.sendEvent(id, "commit", { value });
  }

  submit(): void {
    const buttons = [...this.nodes.values()].filter((n) => n.kind === "button");
    const target = buttons.find((n) => n.emphasis === "primary") ?? buttons[0];
    if (target) this.press(target.id, target.el);
  }

  hrefFor(id: string): string {
    const e = this.current?.edges.find((x) => x.component === id && x.to);
    return e?.to ? `#${e.to.tape}/${e.to.frame}` : "#";
  }

  /** Optimistic feedback: pressed state now, input held until the engine answers. */
  private hold(el: HTMLElement): void {
    this.busy = true;
    this.pressedAt = performance.now();
    el.classList.add("is-pressed");
    el.setAttribute("aria-busy", "true");
    this.content.classList.add("is-busy");
    this.state = "busy";
    clearTimeout(this.busyTimer);
    this.busyTimer = setTimeout(() => {
      this.idle();
      this.toast("Still working on that…");
    }, BUSY_TIMEOUT_MS);
  }

  private idle(): void {
    this.busy = false;
    clearTimeout(this.busyTimer);
    for (const el of this.content.querySelectorAll(".is-pressed")) {
      el.classList.remove("is-pressed");
      el.removeAttribute("aria-busy");
    }
    this.content.classList.remove("is-busy");
    if (this.link.open) this.state = "ready";
  }

  private key(e: KeyboardEvent): void {
    if (e.key === "Escape") {
      const back = this.current?.edges.find((x) => x.kind === "back");
      const node = back && this.nodes.get(back.component);
      if (node) {
        e.preventDefault();
        this.press(node.id, node.el);
      }
    } else if (e.key === "`" && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
      this.hud.toggle();
    }
  }

  private toast(text: string): void {
    this.toastEl.textContent = text;
    this.toastEl.hidden = false;
    clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(() => (this.toastEl.hidden = true), 4000);
  }

  /** For tests and the HUD: drop the socket and let the player reconnect. */
  dropConnection(): void {
    this.link.drop();
  }
}
