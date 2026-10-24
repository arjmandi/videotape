// The intents the engine's tests play, generated from the Python SDK's sample apps (scripts/intents.mjs).

import { readFileSync } from "node:fs";
import { type Intent, loadIntent } from "../src/intent";

export const SAMPLES = ["hello", "relay", "crm", "demo", "pinhole", "screening"] as const;
export type Sample = (typeof SAMPLES)[number];

export function rawIntent(name: string): unknown {
  return JSON.parse(readFileSync(new URL(`./fixtures/${name}.intent.json`, import.meta.url), "utf8"));
}

export function intent(name: string): Intent {
  return loadIntent(rawIntent(name));
}
