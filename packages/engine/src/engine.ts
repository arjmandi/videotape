// The engine core (05 §5), headless: the journey runtime and the documents, played for one app
// through the app protocol. No composer, no scene state, no clients yet: sessions are driven
// in process (see the headless driver), with the same input validation a client protocol will use.

import { randomBytes } from "node:crypto";
import { type AppHost, AppLink } from "./app-link";
import { type DocChange, DocumentStore } from "./documents";
import { IntentError, type Intent, type JsonObject } from "./intent";
import { Places } from "./journey";
import { type Logger, consoleLogger } from "./log";
import { AppMirror } from "./mirror";
import type { DocRef, FetchMessage, SyncMessage, UserRecord } from "./protocol";
import { Records } from "./records";
import { type AppServer, type AppServerOptions, listenForApps } from "./server";
import { type Listener, Session } from "./session";

export interface EngineOptions {
  logger?: Logger;
  /** How long a load or decide may take. */
  timeoutMs?: number;
  /** How long a detached session can be resumed. */
  resumeTtlMs?: number;
}

export interface OpenOptions {
  /** Start at the frame this address opens (05 §6.3), instead of the app's entry. */
  address?: string;
  /** Start at this tape, with these arguments: for tests that begin mid-journey. */
  tape?: string;
  args?: JsonObject;
  /** Start signed in as this user, as if a sign-in had happened: for tests (06 §8.1's `user=`).
   *  Without an address or a tape, a journey the user has resumes, as after a sign-in. */
  user?: UserRecord;
  /** The device the client runs on; reels are keyed by user and device (Q62). A fresh one by default. */
  device?: string;
  /** Hears the session from its first frame on. */
  listener?: Listener;
}

interface Played {
  intent: Intent;
  records: Records;
  places: Places;
  docs: DocumentStore;
}

export class Engine implements AppHost {
  readonly log: Logger;
  readonly timeoutMs: number;
  private readonly resumeTtlMs: number;
  private played: Played | undefined;
  private current: AppLink | undefined;
  private appMirror: AppMirror | undefined;
  private readonly sessions = new Map<string, Session>();
  private readonly byToken = new Map<string, Session>();
  /** Signed-in sessions by user and device: whose journey resumes where (Q62). */
  private readonly journeys = new Map<string, Map<string, Session>>();
  private waiting: Array<() => void> = [];

  constructor(opts: EngineOptions = {}) {
    this.log = opts.logger ?? consoleLogger();
    this.timeoutMs = opts.timeoutMs ?? 30_000;
    this.resumeTtlMs = opts.resumeTtlMs ?? 10 * 60_000;
  }

  private get state(): Played {
    if (!this.played) throw new Error("no app has registered");
    return this.played;
  }

  get intent(): Intent {
    return this.state.intent;
  }
  get records(): Records {
    return this.state.records;
  }
  get places(): Places {
    return this.state.places;
  }
  get docs(): DocumentStore {
    return this.state.docs;
  }
  /** The connected app, if one is connected. */
  get link(): AppLink | undefined {
    return this.current;
  }

  /** What the connected app holds of the documents (Q53). */
  get mirror(): AppMirror | undefined {
    return this.appMirror;
  }

  // ── the app ────────────────────────────────────────────────────────────────

  /** Listens for the app process on a WebSocket (`/app`). */
  listen(opts: AppServerOptions = {}): Promise<AppServer> {
    return listenForApps(this, { logger: this.log, timeoutMs: this.timeoutMs, ...opts });
  }

  /** Resolves when an app has registered. */
  ready(): Promise<void> {
    if (this.current) return Promise.resolve();
    return new Promise((resolve) => this.waiting.push(resolve));
  }

  registered(link: AppLink, intent: Intent): void {
    if (this.played && this.played.intent.app !== intent.app && this.sessions.size > 0) {
      throw new IntentError([`this engine plays ${this.played.intent.app}, which has sessions; ${intent.app} cannot replace it`]);
    }
    if (this.current && this.current !== link) {
      this.log.info("a new connection replaces the app's old one", { app: intent.app });
      const old = this.current;
      this.current = undefined;
      old.close(1012, "replaced");
    }
    if (!this.played || JSON.stringify(this.played.intent) !== JSON.stringify(intent)) {
      const records = new Records(intent);
      const places = new Places(intent, records);
      // A new intent keeps the documents only when the records are the same; sessions continue.
      const keep = this.played && JSON.stringify(this.played.intent.records) === JSON.stringify(intent.records);
      const docs = keep ? this.played!.docs : new DocumentStore(records, this.log);
      if (!keep) {
        docs.onChange((change) => this.fanOut(change));
        docs.onConfirmed((change) => this.appMirror?.confirmed(change));
        docs.onDrop((ref) => this.appMirror?.dropped(ref));
      }
      this.played = { intent, records, places, docs };
    }
    for (const [name, h] of Object.entries(intent.handlers)) {
      if (h.unreadable) this.log.warn("a handler's outcomes cannot be read; deciding with it will fail", { app: intent.app, handler: name });
    }
    this.current = link;
    this.appMirror = new AppMirror(link, this.played.docs, this.played.records);
    const waiting = this.waiting;
    this.waiting = [];
    queueMicrotask(() => waiting.forEach((w) => w()));
  }

  sync(link: AppLink, msg: SyncMessage): void {
    if (link !== this.current || !this.played) return;
    const docs = this.played.docs;
    for (const change of msg.changes) {
      if (msg.decision !== undefined && link.isOpen(msg.decision)) {
        // A decision's changes are tentative; they reach the app's mirror when confirmed (Q68).
        docs.tentative(msg.decision, change.doc, change.ops);
      } else if (msg.decision !== undefined) {
        // A decision that has ended: its changes are the app's own now (Q54), made on a decision's
        // copy rather than the app's mirror, so the mirror gets them as ops.
        docs.apply(change.doc, change.ops, "engine");
      } else {
        // Q54: the app's own changes outside any decision, made through its mirror: echoed.
        const from = docs.get(change.doc)?.cversion;
        const applied = docs.apply(change.doc, change.ops);
        this.appMirror?.echo(change.doc, from, applied.length === change.ops.length);
      }
    }
  }

  forget(link: AppLink, refs: DocRef[]): void {
    if (link === this.current) this.appMirror?.forget(refs);
  }

  fetch(link: AppLink, msg: FetchMessage): void {
    if (link === this.current) this.appMirror?.fetched(msg.id, msg.docs);
  }

  closed(link: AppLink): void {
    if (this.current === link) {
      this.current = undefined;
      this.appMirror = undefined;
    }
  }

  /** Every session that shows a changed document hears of it (05 §6.2: showing is subscribing). */
  private fanOut(change: DocChange): void {
    const ids = new Set<string>();
    for (const holder of change.doc.holders) ids.add(holder.slice(0, holder.indexOf(":")));
    for (const id of ids) {
      const session = this.sessions.get(id);
      if (!session || !session.shows(change.doc.ref)) continue;
      session.emit({
        t: "doc", ref: change.doc.ref, record: change.doc.record, state: change.state, version: change.doc.version,
        ...(change.decision ? { decision: change.decision } : {}),
      });
    }
  }

  // ── sessions ───────────────────────────────────────────────────────────────

  /** Opens a session and plays it to its first frame. */
  async open(opts: OpenOptions = {}): Promise<Session> {
    this.sweep();
    const id = `s_${randomBytes(6).toString("hex")}`;
    const token = randomBytes(24).toString("base64url");
    const device = opts.device ?? `dev_${randomBytes(6).toString("hex")}`;
    const session = new Session(this, id, token, opts.user ?? null, device);
    this.sessions.set(id, session);
    this.byToken.set(token, session);
    if (opts.listener) session.on(opts.listener);
    this.log.info("session started", { session: id });
    const from = opts.user ? this.signedIn(session) : undefined;
    if (from && opts.address === undefined && opts.tape === undefined) {
      session.resumeFrom(from);
      await session.begin({ resume: true });
    } else {
      await session.begin(opts);
    }
    return session;
  }

  // ── reels by user and device (05 §6.2, Q62) ────────────────────────────────

  private static userKey(user: UserRecord): string {
    return `${user.record}#${user.id}`;
  }

  /**
   * A session has signed in: it becomes the journey of its user on its device, and gets the journey
   * to resume, if the user has one: this device's own (an earlier session here, which ends), or else
   * the most recently active one on another device.
   */
  signedIn(session: Session): Session | undefined {
    const user = session.user;
    if (!user) return undefined;
    const key = Engine.userKey(user);
    let devices = this.journeys.get(key);
    if (!devices) this.journeys.set(key, (devices = new Map()));
    const own = devices.get(session.device);
    const others = [...devices.entries()].filter(([d, s]) => d !== session.device && s !== session && !s.closed).map(([, s]) => s);
    devices.set(session.device, session);
    if (own && own !== session && !own.closed) return own;
    return others.sort((a, b) => b.lastActive - a.lastActive)[0];
  }

  /** A session has signed out: it is no longer its user's journey on its device. */
  signedOut(session: Session): void {
    if (!session.user) return;
    const devices = this.journeys.get(Engine.userKey(session.user));
    if (devices?.get(session.device) === session) devices.delete(session.device);
  }

  /** The session a resume token names, while it can still be resumed. */
  resume(token: string): Session | undefined {
    const s = this.byToken.get(token);
    if (!s || s.closed) return undefined;
    if (s.detachedAt !== undefined && Date.now() - s.detachedAt > this.resumeTtlMs) return undefined;
    s.detachedAt = undefined;
    return s;
  }

  /** A client went away: the reel stays, resumable for a while (05 §11, Idle). */
  detach(session: Session): void {
    session.detachedAt = Date.now();
  }

  close(session: Session): void {
    if (session.user) this.signedOut(session);
    session.close();
    this.sessions.delete(session.id);
    this.byToken.delete(session.token);
  }

  get sessionCount(): number {
    return this.sessions.size;
  }

  private sweep(): void {
    const now = Date.now();
    for (const s of this.sessions.values()) {
      if (s.detachedAt !== undefined && now - s.detachedAt > this.resumeTtlMs) this.close(s);
    }
  }
}
