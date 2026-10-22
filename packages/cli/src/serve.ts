// videotape serve | dev (spec §11).

import { type ChildProcess, spawn } from "node:child_process";
import { existsSync, watch } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { Engine, FsCache, consoleLogger, startServer } from "@videotape/engine";
import { loadProject } from "./load";
import { resolveRenderers } from "./renderers";

export interface ServeOptions {
  dev: boolean;
  port?: string | undefined;
  host?: string | undefined;
  renderers?: string | undefined;
  debug?: boolean | undefined;
  cacheOnly?: boolean | undefined;
}

/** The built player, building it first if needed. */
export async function playerDir(): Promise<string> {
  const pkg = dirname(createRequire(import.meta.url).resolve("@videotape/player/package.json"));
  const dist = join(pkg, "dist");
  if (!existsSync(join(dist, "index.html"))) {
    process.stdout.write("building the player…\n");
    const { build } = await import("vite");
    await build({ configFile: join(pkg, "vite.config.ts"), logLevel: "warn" });
  }
  return dist;
}

export async function runServer(dir: string, opts: ServeOptions): Promise<number> {
  if (opts.dev) return runDev(dir, opts);
  const { dir: root, config } = await loadProject(dir);
  const debug = opts.debug ?? config.debug ?? false;
  const logger = consoleLogger(debug ? "debug" : "info");
  const renderers = await resolveRenderers(opts.renderers?.split(",") ?? config.renderers ?? ["flat"], config.rendererOptions ?? {}, logger);
  const engine = new Engine(config, {
    cache: new FsCache(join(root, config.cache ?? ".videotape/cache")),
    logger,
    renderers: renderers.scene,
    ...(renderers.validator ? { validator: renderers.validator } : {}),
    ...(opts.cacheOnly ? { generate: false } : {}),
    debug,
  });
  const server = await startServer({
    engine,
    port: Number(opts.port ?? process.env.PORT ?? 4173),
    hostname: opts.host ?? process.env.HOST ?? "127.0.0.1",
    playerDir: await playerDir(),
    publicDir: join(root, config.publicDir ?? "public"),
  });
  const scenes = renderers.scene.map((r) => `${r.id}${r.available?.() === false ? " (unavailable)" : ""}`).join(" → ");
  process.stdout.write(`videotape ${debug ? "dev" : "serve"} · ${server.url}${debug ? "/?debug=1" : ""} · renderers ${scenes}${opts.cacheOnly ? " · cache only" : ""}\n`);
  const stop = () => void server.close().then(() => process.exit(0));
  process.once("SIGINT", stop);
  process.once("SIGTERM", stop);
  return new Promise(() => {});
}

/** Runs `serve --debug` in a child process and restarts it when the app's files change. */
async function runDev(dir: string, opts: ServeOptions): Promise<number> {
  const { dir: root } = await loadProject(dir);
  await playerDir();
  const bin = fileURLToPath(new URL("../bin/videotape.mjs", import.meta.url));
  const args = [bin, "serve", root, "--debug", ...(opts.port ? ["--port", opts.port] : []), ...(opts.host ? ["--host", opts.host] : []),
    ...(opts.renderers ? ["--renderers", opts.renderers] : []), ...(opts.cacheOnly ? ["--cache-only"] : [])];
  let child: ChildProcess | undefined;
  const start = () => {
    child = spawn(process.execPath, args, { stdio: "inherit" });
  };
  let timer: ReturnType<typeof setTimeout> | undefined;
  watch(root, { recursive: true }, (_event, file) => {
    if (!file || /(^|[/\\])(node_modules|\.videotape|test|dist)([/\\]|$)/.test(file) || !/\.(ts|js|mjs|json)$/.test(file)) return;
    clearTimeout(timer);
    timer = setTimeout(() => {
      process.stdout.write(`\n↻ ${relative(process.cwd(), join(root, file))} changed; restarting\n`);
      child?.once("exit", start);
      child?.kill("SIGTERM");
    }, 120);
  });
  start();
  const stop = () => {
    child?.kill("SIGTERM");
    process.exit(0);
  };
  process.once("SIGINT", stop);
  process.once("SIGTERM", stop);
  return new Promise(() => {});
}
