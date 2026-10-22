// A fake transport for driving the engine in-process.

import type { App, RenderMessage, ServerMessage, Services } from "@videotape/core";
import { type Cache, Engine, type EngineOptions, MemoryCache, memoryLogger } from "../src";

export interface Harness {
  engine: Engine;
  sent: ServerMessage[];
  log: ReturnType<typeof memoryLogger>;
  hello(viewport?: { w: number; h: number }, resume?: string): Promise<void>;
  send(msg: Record<string, unknown>): Promise<void>;
  press(component: string, values?: Record<string, unknown>): Promise<void>;
  select(component: string, item: string): Promise<void>;
  render(): RenderMessage;
  /** Messages since the last call. */
  take(): ServerMessage[];
  reconnect(): Harness;
  nextSeq(): number;
}

export function harness(app: App, services: Services = {} as Services, opts: EngineOptions & { cache?: Cache } = {}): Harness {
  const log = memoryLogger();
  const engine = new Engine({ app, services }, { logger: log, cache: new MemoryCache(), ...opts });
  return attach(engine, log);
}

export function attach(engine: Engine, log: ReturnType<typeof memoryLogger>): Harness {
  const sent: ServerMessage[] = [];
  let taken = 0;
  let seq = 0;
  const conn = engine.connect((m) => sent.push(m));
  const h: Harness = {
    engine,
    sent,
    log,
    hello: (viewport = { w: 1440, h: 900 }, resume) =>
      conn.receive(JSON.stringify({
        t: "hello", v: 1, viewport: { ...viewport, dpr: 1 }, caps: { video: ["webm"], webrtc: false }, ...(resume ? { resume } : {}),
      })),
    send: (msg) => conn.receive(JSON.stringify(msg)),
    press: (component, values) =>
      conn.receive(JSON.stringify({ t: "event", seq: ++seq, render: h.render().seq, component, type: "press", ...(values ? { values } : {}) })),
    select: (component, item) =>
      conn.receive(JSON.stringify({ t: "event", seq: ++seq, render: h.render().seq, component, type: "select", value: item })),
    render: () => {
      const r = [...sent].reverse().find((m): m is RenderMessage => m.t === "render");
      if (!r) throw new Error("no render yet");
      return r;
    },
    take: () => {
      const out = sent.slice(taken);
      taken = sent.length;
      return out;
    },
    reconnect: () => {
      conn.close();
      return attach(engine, log);
    },
    nextSeq: () => ++seq,
  };
  return h;
}

/** Waits for fire-and-forget work (prefetch, pending patches) to settle. */
export const settle = (ms = 20) => new Promise((r) => setTimeout(r, ms));
