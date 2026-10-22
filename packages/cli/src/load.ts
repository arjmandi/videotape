// Finds and imports an app's videotape.config.ts (or, failing that, its tapes.ts).

import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import type { App } from "@videotape/core";
import type { VideotapeConfig } from "@videotape/engine";

export interface Project {
  dir: string;
  config: VideotapeConfig;
}

export async function loadProject(dirArg = "."): Promise<Project> {
  const dir = resolve(dirArg);
  for (const name of ["videotape.config.ts", "videotape.config.js", "videotape.config.mjs"]) {
    const file = join(dir, name);
    if (existsSync(file)) {
      const mod = (await import(pathToFileURL(file).href)) as { default?: VideotapeConfig };
      if (!mod.default?.app) throw new Error(`${file} must default-export a config with an \`app\``);
      return { dir, config: mod.default };
    }
  }
  const tapes = join(dir, "tapes.ts");
  if (existsSync(tapes)) {
    const mod = (await import(pathToFileURL(tapes).href)) as { default?: App };
    if (!mod.default) throw new Error(`${tapes} must default-export an app`);
    return { dir, config: { app: mod.default } };
  }
  throw new Error(`no videotape.config.ts or tapes.ts in ${dir}`);
}
