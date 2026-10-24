// Runs a sample app's Python process against an engine, as `videotape serve` does in production.

import { type ChildProcess, spawn } from "node:child_process";
import { APPS, REPO, python } from "../scripts/python.mjs";

export const PYTHON = python();
/** Integration tests need the SDK's Python; without it they are skipped, and say so. */
export const NO_PYTHON = PYTHON === undefined;

export interface AppProcess {
  proc: ChildProcess;
  output: string[];
  stop(): Promise<void>;
}

export function startApp(name: string, engineUrl: string): AppProcess {
  if (!PYTHON) throw new Error("no Python with the SDK: create sdk/python/.venv or set VIDEOTAPE_PYTHON");
  const [dir, target] = APPS[name]!;
  const proc = spawn(PYTHON, ["-m", "videotape.cli", "serve", target, "--app-dir", `${REPO}${dir}`, "--engine", engineUrl, "--once"], {
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
  });
  const output: string[] = [];
  proc.stdout?.on("data", (d) => output.push(String(d)));
  proc.stderr?.on("data", (d) => output.push(String(d)));
  return {
    proc,
    output,
    stop: () =>
      new Promise<void>((resolve) => {
        if (proc.exitCode !== null || proc.signalCode !== null) return resolve();
        proc.once("exit", () => resolve());
        proc.kill("SIGTERM");
      }),
  };
}
