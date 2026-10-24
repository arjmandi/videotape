// The engine's WebSocket endpoint for app processes (05 §6.6): apps connect out to `/app`.

import type { AddressInfo } from "node:net";
import { WebSocketServer } from "ws";
import { type AppHost, AppLink } from "./app-link";
import { type Logger, consoleLogger } from "./log";
import { MAX_MESSAGE_CHARS } from "./protocol";

export interface AppServerOptions {
  port?: number;
  host?: string;
  path?: string;
  logger?: Logger;
  timeoutMs?: number;
}

export interface AppServer {
  port: number;
  url: string;
  close(): Promise<void>;
}

/** Listens for app processes; each connection becomes an AppLink played by `host`. */
export async function listenForApps(host: AppHost, opts: AppServerOptions = {}): Promise<AppServer> {
  const logger = opts.logger ?? consoleLogger();
  const path = opts.path ?? "/app";
  const wss = new WebSocketServer({ port: opts.port ?? 0, host: opts.host ?? "127.0.0.1", path, maxPayload: MAX_MESSAGE_CHARS });
  await new Promise<void>((resolve, reject) => {
    wss.once("listening", resolve);
    wss.once("error", reject);
  });
  wss.on("connection", (ws) => {
    const link = new AppLink(host, {
      send: (text) => ws.send(text),
      close: (code, reason) => ws.close(code, reason),
    }, { logger, ...(opts.timeoutMs !== undefined ? { timeoutMs: opts.timeoutMs } : {}) });
    ws.on("message", (data, isBinary) => {
      if (isBinary) {
        logger.warn("dropped a binary message from an app");
        return;
      }
      link.receive(data.toString());
    });
    ws.on("close", () => link.closed());
    ws.on("error", (e) => logger.warn("app connection error", { error: e.message }));
  });
  const { port } = wss.address() as AddressInfo;
  return {
    port,
    url: `ws://${opts.host ?? "127.0.0.1"}:${port}${path}`,
    close: () =>
      new Promise<void>((resolve) => {
        for (const client of wss.clients) client.terminate();
        wss.close(() => resolve());
      }),
  };
}
