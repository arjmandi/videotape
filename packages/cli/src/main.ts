// videotape dev | serve | check | graph | render | schema (spec §11).

import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { parseArgs } from "node:util";
import { type Diagnostic, buildGraph, check, jsonSchemas, toMermaid, toSpec } from "@videotape/core";
import { loadProject } from "./load";

const HELP = `videotape — interfaces, played.

Usage: videotape <command> [dir] [options]

  check  [dir]                          validate the app; exit code 1 on errors
  graph  [dir] [--format mermaid|json]  print the journey graph
  schema [--out dir]                    print or write JSON Schemas for tapes and VTP
  dev    [dir] [--port n] [--renderers a,b] [--cache-only]   engine with reload and debug on
  serve  [dir] [--port n] [--renderers a,b] [--cache-only]   production engine; --cache-only never generates
  render [dir] [--viewports a,b] [--renderers a,b] [--frames tape,tape/frame] [--sheet out.png]
                                        ahead-of-time render into the cache
`;

export async function main(argv: string[]): Promise<number> {
  const [command, ...rest] = argv;
  const { values, positionals } = parseArgs({
    args: rest,
    allowPositionals: true,
    options: {
      format: { type: "string", default: "mermaid" },
      out: { type: "string" },
      port: { type: "string" },
      host: { type: "string" },
      renderers: { type: "string" },
      viewports: { type: "string" },
      frames: { type: "string" },
      "cache-only": { type: "boolean" },
      sheet: { type: "string" },
      debug: { type: "boolean" },
    },
  });
  const dir = positionals[0] ?? ".";

  try {
    switch (command) {
      case "check": return await runCheck(dir);
      case "graph": return await runGraph(dir, values.format!);
      case "schema": return runSchema(values.out);
      case "dev": case "serve": {
        const { runServer } = await import("./serve");
        return await runServer(dir, {
          dev: command === "dev", port: values.port, host: values.host, renderers: values.renderers, debug: values.debug,
          cacheOnly: values["cache-only"],
        });
      }
      case "render": {
        const { runRender } = await import("./render");
        return await runRender(dir, { renderers: values.renderers, viewports: values.viewports, frames: values.frames, sheet: values.sheet });
      }
      case undefined: case "help": case "--help": case "-h":
        process.stdout.write(HELP);
        return 0;
      default:
        process.stderr.write(`unknown command "${command}"\n\n${HELP}`);
        return 2;
    }
  } catch (e) {
    process.stderr.write(`videotape: ${e instanceof Error ? e.message : String(e)}\n`);
    return 1;
  }
}

export function formatDiagnostics(diags: Diagnostic[]): string {
  const width = Math.max(0, ...diags.map((d) => d.code.length));
  const lines = diags.map((d) =>
    `${d.level === "error" ? "✖ error  " : "⚠ warning"}  ${d.code.padEnd(width)}  ${d.at ? `${d.at}  ` : ""}${d.message}`);
  const errors = diags.filter((d) => d.level === "error").length;
  const warnings = diags.length - errors;
  lines.push(`${errors} error${errors === 1 ? "" : "s"}, ${warnings} warning${warnings === 1 ? "" : "s"}`);
  return lines.join("\n") + "\n";
}

async function runCheck(dir: string): Promise<number> {
  const { config } = await loadProject(dir);
  const diags = check(config.app);
  const frames = config.app.tapes.reduce((n, t) => n + t.frames.length, 0);
  if (diags.length === 0) {
    process.stdout.write(`✔ ${config.app.tapes.length} tapes, ${frames} frames: no problems\n`);
    return 0;
  }
  process.stdout.write(formatDiagnostics(diags));
  return diags.some((d) => d.level === "error") ? 1 : 0;
}

async function runGraph(dir: string, format: string): Promise<number> {
  const { config } = await loadProject(dir);
  const g = buildGraph(toSpec(config.app));
  if (format === "json") process.stdout.write(JSON.stringify(g, null, 2) + "\n");
  else if (format === "mermaid") process.stdout.write(toMermaid(g));
  else throw new Error(`unknown graph format "${format}" (mermaid, json)`);
  return 0;
}

function runSchema(out: string | undefined): number {
  const schemas = jsonSchemas();
  if (!out) {
    process.stdout.write(JSON.stringify(schemas, null, 2) + "\n");
    return 0;
  }
  const dir = resolve(out);
  mkdirSync(dir, { recursive: true });
  for (const [name, schema] of Object.entries(schemas)) writeFileSync(join(dir, `${name}.schema.json`), JSON.stringify(schema, null, 2) + "\n");
  process.stdout.write(`wrote ${Object.keys(schemas).length} schemas to ${dir}\n`);
  return 0;
}
