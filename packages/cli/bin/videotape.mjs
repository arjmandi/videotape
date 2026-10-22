#!/usr/bin/env node
// Runs the TypeScript CLI through tsx so apps can write tapes and config in TypeScript.
import { register } from "tsx/esm/api";

register();
// Piping into `head` closes stdout early; that is not an error.
process.stdout.on("error", (e) => {
  if (e.code === "EPIPE") process.exit(0);
  throw e;
});
const { main } = await import("../src/main.ts");
process.exitCode = await main(process.argv.slice(2));
