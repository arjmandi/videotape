import { defineConfig } from "@videotape/engine";
import { services } from "./services";
import app from "./tapes";

export default defineConfig({
  app,
  services,
  // Preference order; flat is always the fallback. Try generated scenes with
  // `FAL_KEY=… videotape dev apps/site --renderers still-fal`.
  renderers: ["flat"],
  rendererOptions: { "still-fal": { strength: 0.82 } },
  // The dashboard's scene follows the user's plan; render both moods ahead of time.
  aheadSamples: [{}, { user: { plan: "pro" } }],
});
