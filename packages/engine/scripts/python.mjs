// Where the Python SDK is, for the script that regenerates intents and for the tests that run apps.

import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

export const REPO = fileURLToPath(new URL("../../../", import.meta.url));
export const SDK = `${REPO}sdk/python`;

/** The Python that has the SDK installed: $VIDEOTAPE_PYTHON, or the SDK's own virtualenv. */
export function python() {
  const fromEnv = process.env.VIDEOTAPE_PYTHON;
  if (fromEnv) return fromEnv;
  const venv = `${SDK}/.venv/bin/python`;
  return existsSync(venv) ? venv : undefined;
}

/** The sample apps the engine's tests play: name → [directory under the repo, module:app]. */
export const APPS = {
  hello: ["sdk/python/tests/fixtures/hello", "app:app"],
  relay: ["sdk/python/tests/fixtures/apps", "relay"],
  crm: ["sdk/python/tests/fixtures/apps", "crm"],
  demo: ["sdk/python/tests/fixtures/apps", "demo"],
  pinhole: ["sdk/python/tests/fixtures/apps", "pinhole"],
  screening: ["sdk/python/tests/fixtures/apps", "screening"],
  journeys: ["packages/engine/test/apps", "journeys"],
};
