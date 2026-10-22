#!/usr/bin/env node
// Runs the TypeScript CLI through tsx so apps can write tapes and config in TypeScript.
import { existsSync } from "node:fs";
import { register } from "tsx/esm/api";

// Backend credentials come from the environment (spec §11). A gitignored .env in the
// directory you run from is loaded into it; variables already set win.
if (existsSync(".env")) process.loadEnvFile(".env");

register();
// Piping into `head` closes stdout early; that is not an error.
process.stdout.on("error", (e) => {
  if (e.code === "EPIPE") process.exit(0);
  throw e;
});
const { main } = await import("../src/main.ts");
process.exitCode = await main(process.argv.slice(2));
