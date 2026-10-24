// The engine's end of one app connection (05 §6.6). Transport-free, as prototype-0's Connection was:
// `receive` takes raw text from the app and the transport's `send` takes text for it, so tests drive
// it in memory and the server wraps it in a WebSocket.

import { IntentError, type Intent, loadIntent } from "./intent";
import { type Logger, scrub } from "./log";
import {
  APP_PROTOCOL_VERSION, type AppRequest, type DecideRequest, type DocRef, type EngineMessage, type FetchMessage,
  type LoadRequest, type LogMessage, type PageRequest, type ResultMessage, type SyncMessage, decodeAppMessage,
} from "./protocol";

export interface Transport {
  send(text: string): void;
  close(code?: number, reason?: string): void;
}

/** What the engine does with an app connection's messages. */
export interface AppHost {
  /** The app sent a valid intent. Throw an IntentError to refuse it. */
  registered(link: AppLink, intent: Intent): void;
  /** Document changes: tentative under `msg.decision`, or confirmed. */
  sync(link: AppLink, msg: SyncMessage): void;
  /** The app dropped its copy of these documents. */
  forget(link: AppLink, docs: DocRef[]): void;
  /** The app asks for documents it does not hold. */
  fetch(link: AppLink, msg: FetchMessage): void;
  /** The connection ended; every request still open has failed. */
  closed(link: AppLink): void;
}

/** A request the app did not answer: it went away, or took too long. */
export class AppUnavailable extends Error {
  constructor(readonly code: "app_gone" | "app_timeout", message: string) {
    super(message);
    this.name = "AppUnavailable";
  }
}

export interface AppLinkOptions {
  logger: Logger;
  /** How long a load or decide may take before it fails. */
  timeoutMs?: number;
}

interface Pending {
  request: AppRequest;
  resolve: (r: ResultMessage) => void;
  reject: (e: Error) => void;
  timer: ReturnType<typeof setTimeout>;
  secrets: string[];
}

type Ask<T extends AppRequest> = Omit<T, "id" | "t">;

export class AppLink {
  intent: Intent | undefined;
  private next = 0;
  private readonly pending = new Map<string, Pending>();
  private open = true;
  private readonly timeoutMs: number;
  private readonly log: Logger;

  constructor(private readonly host: AppHost, private readonly transport: Transport, opts: AppLinkOptions) {
    this.log = opts.logger;
    this.timeoutMs = opts.timeoutMs ?? 30_000;
  }

  get registered(): boolean {
    return this.intent !== undefined;
  }

  get app(): string | undefined {
    return this.intent?.app;
  }

  /** Whether a decision is still waiting for its result, so its changes may be tentative. */
  isOpen(decision: string): boolean {
    return this.pending.get(decision)?.request.t === "decide";
  }

  /** The secret values the requests in flight carry: what the app's words are scrubbed of. */
  secretsInPlay(): string[] {
    return [...this.pending.values()].flatMap((p) => p.secrets);
  }

  // ── requests ───────────────────────────────────────────────────────────────

  load(req: Ask<LoadRequest>): Promise<ResultMessage> {
    return this.request({ ...req, t: "load" }, []);
  }

  page(req: Ask<PageRequest>): Promise<ResultMessage> {
    return this.request({ ...req, t: "page" }, []);
  }

  /** Asks the app to run a handler. `secrets` are the secret values its documents carry. */
  decide(req: Ask<DecideRequest>, secrets: string[] = [], onId?: (id: string) => void): Promise<ResultMessage> {
    return this.request({ ...req, t: "decide" }, secrets, onId);
  }

  private request(body: Omit<AppRequest, "id">, secrets: string[], onId?: (id: string) => void): Promise<ResultMessage> {
    if (!this.open || !this.registered) return Promise.reject(new AppUnavailable("app_gone", "the app is not connected"));
    const id = `r${++this.next}`;
    const request = { ...body, id } as AppRequest;
    onId?.(id);
    return new Promise<ResultMessage>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        this.log.warn("the app did not answer in time", { request: id, t: request.t, name: nameOf(request), ms: this.timeoutMs });
        reject(new AppUnavailable("app_timeout", `the app did not answer ${request.t} in ${this.timeoutMs} ms`));
      }, this.timeoutMs);
      this.pending.set(id, { request, resolve, reject, timer, secrets });
      this.send(request);
    });
  }

  send(msg: EngineMessage): void {
    if (!this.open) return;
    this.transport.send(JSON.stringify(msg));
  }

  // ── messages from the app ──────────────────────────────────────────────────

  receive(raw: string): void {
    const decoded = decodeAppMessage(raw);
    if (!decoded.ok) {
      this.log.warn("dropped a message from the app", { app: this.app, reason: decoded.reason });
      this.send({ t: "error", code: "bad_message", message: decoded.reason });
      return;
    }
    const msg = decoded.msg;
    if (msg.t === "ping") return this.send({ t: "pong" });
    if (msg.t === "register") {
      if (this.registered) {
        this.send({ t: "error", code: "already_registered", message: "this connection has registered its app" });
        return;
      }
      try {
        const intent = loadIntent(msg.intent);
        this.host.registered(this, intent);
        this.intent = intent;
      } catch (e) {
        const message = e instanceof IntentError ? e.issues.join("; ") : e instanceof Error ? e.message : String(e);
        this.log.error("refused an app", { reason: message.slice(0, 500) });
        this.send({ t: "error", code: e instanceof IntentError ? "bad_intent" : "refused", message });
        this.close(1008, "refused");
        return;
      }
      this.log.info("app registered", { app: this.intent.app, sdk: `${msg.sdk.language} ${msg.sdk.version}` });
      this.send({ t: "registered", v: APP_PROTOCOL_VERSION, app: this.intent.app });
      return;
    }
    if (!this.registered) {
      this.send({ t: "error", code: "not_registered", message: "send register first" });
      return;
    }
    switch (msg.t) {
      case "result": {
        const p = this.pending.get(msg.id);
        if (!p) {
          this.log.warn("a result for no open request", { app: this.app, request: msg.id });
          return;
        }
        this.pending.delete(msg.id);
        clearTimeout(p.timer);
        p.resolve(msg);
        return;
      }
      case "sync":
        this.host.sync(this, msg);
        return;
      case "log":
        return this.appLog(msg);
      case "forget":
        return this.host.forget(this, msg.docs);
      case "fetch":
        return this.host.fetch(this, msg);
    }
  }

  private appLog(msg: LogMessage): void {
    const text = scrub(msg.message, this.secretsInPlay());
    const fields = { app: this.app, logger: msg.logger };
    if (msg.level === "error") this.log.error(`app: ${text}`, fields);
    else if (msg.level === "warning") this.log.warn(`app: ${text}`, fields);
    else if (msg.level === "info") this.log.info(`app: ${text}`, fields);
    else this.log.debug(`app: ${text}`, fields);
  }

  // ── closing ────────────────────────────────────────────────────────────────

  /** Ends the connection from the engine's side. */
  close(code = 1000, reason = "bye"): void {
    if (!this.open) return;
    this.transport.close(code, reason);
    this.closed();
  }

  /** The transport ended: every open request fails. */
  closed(): void {
    if (!this.open) return;
    this.open = false;
    for (const [id, p] of this.pending) {
      clearTimeout(p.timer);
      p.reject(new AppUnavailable("app_gone", `the app went away during ${p.request.t} ${id}`));
    }
    this.pending.clear();
    if (this.registered) this.log.info("app disconnected", { app: this.app });
    this.host.closed(this);
  }
}

function nameOf(r: AppRequest): string {
  return r.t === "decide" ? r.handler : r.loader;
}
