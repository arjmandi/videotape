// Regenerates test/fixtures/<app>.intent.json from the Python SDK, so the engine's tests read
// exactly what the SDK produces. Run it after changing a sample app:
//
//   npx -y pnpm@9.15.0 --filter @videotape/engine intents
//
// With --check it writes nothing and exits 1 when a fixture is out of date.

import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { APPS, REPO, python } from "./python.mjs";

export function intentOf(name) {
  const py = python();
  if (!py) throw new Error("no Python with the SDK: create sdk/python/.venv or set VIDEOTAPE_PYTHON");
  const [dir, target] = APPS[name];
  return execFileSync(py, ["-m", "videotape.cli", "intent", target, "--app-dir", `${REPO}${dir}`], { encoding: "utf8" });
}

export const fixturePath = (name) => new URL(`../test/fixtures/${name}.intent.json`, import.meta.url);

if (import.meta.url === `file://${process.argv[1]}`) {
  const check = process.argv.includes("--check");
  let stale = 0;
  for (const name of Object.keys(APPS)) {
    const fresh = intentOf(name);
    let old = "";
    try {
      old = readFileSync(fixturePath(name), "utf8");
    } catch {}
    if (old === fresh) continue;
    stale += 1;
    if (check) console.log(`${name}: out of date`);
    else {
      writeFileSync(fixturePath(name), fresh);
      console.log(`${name}: written`);
    }
  }
  if (check && stale) process.exit(1);
}
