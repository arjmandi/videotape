// Plays a sample app for tests: an engine, its /app endpoint, and the app's Python process; or an
// engine with a fake app in memory. `Client` is a thin client over a session, by action ids.

import { AppLink } from "../src/app-link";
import { Engine, type OpenOptions } from "../src/engine";
import { type LogLine, memoryLogger } from "../src/log";
import type { AppRequest, ResultMessage } from "../src/protocol";
import type { FrameView, Input, Session, SessionEvent } from "../src/session";
import { rawIntent } from "./fixtures";
import { type AppProcess, startApp } from "./python";

export interface Played {
  engine: Engine;
  lines: LogLine[];
  app: AppProcess;
  stop(): Promise<void>;
}

/** An engine playing a sample app's Python process. */
export async function play(name: string, opts: { timeoutMs?: number } = {}): Promise<Played> {
  const logger = memoryLogger();
  const engine = new Engine({ logger, ...opts });
  const server = await engine.listen();
  const app = startApp(name, server.url);
  const ready = engine.ready();
  const exited = new Promise<never>((_, reject) => app.proc.once("exit", (code) => reject(new Error(`the app exited (${code}): ${app.output.join("")}`))));
  await Promise.race([ready, exited]);
  return {
    engine,
    lines: logger.lines,
    app,
    stop: async () => {
      await app.stop();
      await server.close();
    },
  };
}

type Reply = Omit<ResultMessage, "t" | "id"> | Record<string, unknown>;

export interface FakeApp {
  engine: Engine;
  lines: LogLine[];
  link: AppLink;
  requests: AppRequest[];
  /** Sends changes as the app would; tentative when `decision` is given. */
  sync(changes: unknown[], decision?: string): void;
  /** The app goes away. */
  disconnect(): void;
}

/** An engine with an app in memory that answers each request with `answer` (or never, for "hang"). */
export function fake(name: string, answer: (req: AppRequest, app: FakeApp) => Reply | "hang" | Promise<Reply | "hang">, opts: { timeoutMs?: number } = {}): FakeApp {
  const logger = memoryLogger();
  const engine = new Engine({ logger, ...opts });
  const requests: AppRequest[] = [];
  let open = true;
  const app = {} as FakeApp;
  const link: AppLink = new AppLink(engine, {
    send: (text) => {
      const msg = JSON.parse(text);
      if (msg.t !== "load" && msg.t !== "decide" && msg.t !== "page") return;
      requests.push(msg);
      void Promise.resolve(answer(msg, app)).then((reply) => {
        if (reply === "hang" || !open) return;
        link.receive(JSON.stringify({ t: "result", id: msg.id, ...reply }));
      });
    },
    close: () => {
      open = false;
    },
  }, { logger, timeoutMs: opts.timeoutMs ?? 5_000 });
  Object.assign(app, {
    engine, lines: logger.lines, link, requests,
    sync: (changes: unknown[], decision?: string) => link.receive(JSON.stringify({ t: "sync", changes, ...(decision ? { decision } : {}) })),
    disconnect: () => {
      open = false;
      link.closed();
    },
  });
  link.receive(JSON.stringify({ t: "register", v: 1, intent: rawIntent(name), sdk: { language: "test", version: "0" } }));
  return app;
}

type Body<T> = T extends unknown ? Omit<T, "seq" | "frame"> : never;

/** A thin client: numbers its inputs, names the frame it saw, and records what the session said. */
export class Client {
  events: SessionEvent[] = [];
  private seq = 0;

  /** A client of a session; `events` are what it heard before (its first frame), if it listened. */
  constructor(readonly session: Session, events?: SessionEvent[]) {
    if (events) this.events = events;
    else session.on((e) => this.events.push(e));
  }

  /** Opens a session on `engine` and hears it from its first frame. */
  static async open(engine: Engine, opts: OpenOptions = {}): Promise<Client> {
    const events: SessionEvent[] = [];
    const session = await engine.open({ ...opts, listener: (e) => events.push(e) });
    return new Client(session, events);
  }

  get view(): FrameView {
    return this.session.view();
  }

  get place(): string {
    return this.session.reel.place;
  }

  send(body: Body<Input>, frame = this.session.version): Promise<void> {
    return this.session.input({ ...body, seq: ++this.seq, frame } as Input);
  }

  fill(field: string, value: unknown) {
    return this.send({ t: "fill", field, value });
  }

  /** Presses an action by id, or by its label. */
  press(action: string, extra: { item?: string; secrets?: Record<string, string> } = {}) {
    const found = this.view.actions.find((a) => a.id === action || a.label === action);
    return this.send({ t: "press", action: found?.id ?? action, ...extra });
  }

  back() {
    return this.send({ t: "back" });
  }

  door(tape: string) {
    return this.send({ t: "hub", tape });
  }

  doc(slot: string): any {
    const ref = this.session.ref(slot);
    return ref ? this.session["engine"].docs.read(ref) : undefined;
  }

  dropped(): string[] {
    return this.events.flatMap((e) => (e.t === "dropped" ? [e.reason] : []));
  }

  effects() {
    return this.events.flatMap((e) => (e.t === "effect" ? [e.effect] : []));
  }

  /** The key of the item at `index` in a list field of a slot's document, as the engine keyed it. */
  key(slot: string, field: string, index: number): string {
    const ref = this.session.ref(slot)!;
    const value = this.session["engine"].docs.get(ref)!.value as any;
    return (field ? value[field] : value)[index]["@key"];
  }
}

export const ADA = { record: "Person", id: "p1", value: { id: "p1", name: "Ada" } };
