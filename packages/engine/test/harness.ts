// Plays a sample app for tests: an engine, its /app endpoint, and the app's Python process; or an
// engine with a fake app in memory. Sessions are driven with the headless driver (src/driver.ts).

import { AppLink } from "../src/app-link";
import { Engine } from "../src/engine";
import { type LogLine, memoryLogger } from "../src/log";
import type { AppRequest, ResultMessage } from "../src/protocol";
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

export const ADA = { record: "Person", id: "p1", value: { id: "p1", name: "Ada" } };
