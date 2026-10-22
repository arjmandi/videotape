// HTTP and WebSocket transport (spec §9): VTP over /vtp, content-addressed
// assets under /a/, the app's own assets under /app/, and the player at /.

import { readFile } from "node:fs/promises";
import type { AddressInfo } from "node:net";
import { extname, normalize, resolve, sep } from "node:path";
import { serve } from "@hono/node-server";
import { createNodeWebSocket } from "@hono/node-ws";
import { type Context, Hono } from "hono";
import { MAX_MESSAGE_CHARS } from "@videotape/core";
import { ASSET_FILE } from "./cache";
import type { Connection, Engine } from "./engine";

const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp",
  ".woff2": "font/woff2", ".ico": "image/x-icon", ".webm": "video/webm", ".mp4": "video/mp4", ".map": "application/json",
};

export interface ServerOptions {
  engine: Engine;
  port?: number;
  hostname?: string;
  /** The built player: index.html and assets/. */
  playerDir?: string;
  /** App assets, served at /app/. */
  publicDir?: string;
}

export interface RunningServer {
  port: number;
  url: string;
  close(): Promise<void>;
}

/** Player CSP (spec §10): no inline scripts, media and images from this origin only. */
function csp(c: Context): string {
  const host = c.req.header("host") ?? "";
  return [
    "default-src 'self'", "script-src 'self'", "style-src 'self'", "img-src 'self' data:", "media-src 'self' blob:",
    `connect-src 'self' ws://${host} wss://${host}`, "font-src 'self'", "object-src 'none'", "base-uri 'none'", "frame-ancestors 'none'",
  ].join("; ");
}

/** Resolves `rel` inside `root`, or undefined if it escapes. */
function inside(root: string, rel: string): string | undefined {
  const base = resolve(root);
  const full = resolve(base, normalize(rel).replace(/^([/\\])+/, ""));
  return full === base || full.startsWith(base + sep) ? full : undefined;
}

async function file(c: Context, root: string | undefined, rel: string, cache: string): Promise<Response> {
  const path = root && inside(root, rel);
  if (!path) return c.notFound();
  try {
    const body = await readFile(path);
    const type = MIME[extname(path)] ?? "application/octet-stream";
    const headers: Record<string, string> = { "content-type": type, "cache-control": cache, "x-content-type-options": "nosniff" };
    if (type.startsWith("text/html")) headers["content-security-policy"] = csp(c);
    return new Response(body, { headers });
  } catch {
    return c.notFound();
  }
}

export function createApp(opts: ServerOptions) {
  const { engine } = opts;
  const app = new Hono();
  const ws = createNodeWebSocket({ app });
  // Larger frames are rejected by the schema anyway; stop them at the socket.
  (ws.wss.options as { maxPayload?: number }).maxPayload = MAX_MESSAGE_CHARS * 4;

  app.get("/healthz", (c) => c.json({ ok: true, reels: engine.reelCount }));

  app.get("/a/:file", async (c) => {
    const name = c.req.param("file");
    if (!ASSET_FILE.test(name)) return c.notFound();
    const asset = await engine.cache.getAsset(name);
    if (!asset) return c.notFound();
    return new Response(asset.bytes, {
      headers: {
        "content-type": asset.mime,
        "cache-control": "public, max-age=31536000, immutable",
        "x-content-type-options": "nosniff",
      },
    });
  });

  app.get("/app/*", (c) => file(c, opts.publicDir, c.req.path.slice("/app/".length), "public, max-age=300"));

  app.get(
    "/vtp",
    ws.upgradeWebSocket((c) => {
      const origin = c.req.header("origin");
      const host = c.req.header("host");
      let conn: Connection | undefined;
      return {
        onOpen(_evt, socket) {
          // No cookies are used, but a page on another origin still has no business driving a reel.
          if (origin && host && new URL(origin).host !== host) {
            socket.close(1008, "origin not allowed");
            return;
          }
          conn = engine.connect((m) => socket.send(JSON.stringify(m)));
        },
        onMessage(evt) {
          void conn?.receive(typeof evt.data === "string" ? evt.data : String(evt.data));
        },
        onClose() {
          conn?.close();
        },
      };
    }),
  );

  app.get("/assets/*", (c) => file(c, opts.playerDir, c.req.path.slice(1), "public, max-age=31536000, immutable"));
  app.get("/", (c) => file(c, opts.playerDir, "index.html", "no-cache"));
  app.get("/favicon.svg", (c) => file(c, opts.playerDir, "favicon.svg", "public, max-age=86400"));

  return { app, injectWebSocket: ws.injectWebSocket };
}

export function startServer(opts: ServerOptions): Promise<RunningServer> {
  const { app, injectWebSocket } = createApp(opts);
  return new Promise((resolveStart) => {
    const server = serve({ fetch: app.fetch, port: opts.port ?? 4173, hostname: opts.hostname ?? "127.0.0.1" }, (info: AddressInfo) => {
      const host = info.family === "IPv6" ? `[${info.address}]` : info.address;
      resolveStart({
        port: info.port,
        url: `http://${host}:${info.port}`,
        close: () => new Promise<void>((done) => {
          (server as unknown as { closeAllConnections?: () => void }).closeAllConnections?.();
          server.close(() => done());
        }),
      });
    });
    injectWebSocket(server);
  });
}

