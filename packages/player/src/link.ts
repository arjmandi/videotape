// The VTP socket with reconnect and backoff (spec §8, Degradation).

import { type ClientMessage, ClientMessageSchema, type ServerMessage, ServerMessageSchema, decode } from "@videotape/core";

export interface LinkEvents {
  open(): void;
  message(m: ServerMessage): void;
  down(): void;
}

const BACKOFF = [250, 500, 1000, 2000, 4000, 8000];

export class Link {
  private ws: WebSocket | undefined;
  private attempt = 0;
  private timer: ReturnType<typeof setTimeout> | undefined;

  constructor(private readonly url: string, private readonly on: LinkEvents) {}

  connect(): void {
    clearTimeout(this.timer);
    const ws = new WebSocket(this.url);
    this.ws = ws;
    ws.addEventListener("open", () => {
      this.attempt = 0;
      this.on.open();
    });
    ws.addEventListener("message", (e) => {
      const r = decode(ServerMessageSchema, String(e.data));
      if (r.ok) this.on.message(r.msg);
      else console.warn("[videotape] ignored a message the schema rejects:", r.reason);
    });
    ws.addEventListener("close", () => {
      if (this.ws !== ws) return;
      this.on.down();
      const wait = BACKOFF[Math.min(this.attempt++, BACKOFF.length - 1)]!;
      this.timer = setTimeout(() => this.connect(), wait);
    });
  }

  get open(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  send(m: ClientMessage): boolean {
    const checked = ClientMessageSchema.safeParse(m);
    if (!checked.success) {
      console.warn("[videotape] refusing to send an invalid message", checked.error.issues);
      return false;
    }
    if (!this.open) return false;
    this.ws!.send(JSON.stringify(checked.data));
    return true;
  }

  /** Drops the socket; the close handler reconnects. For tests and the HUD. */
  drop(): void {
    this.ws?.close();
  }
}
