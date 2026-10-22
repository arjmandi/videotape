import { defineConfig } from "@videotape/engine";
import { services } from "./services";
import app from "./tapes";

export default defineConfig({
  app,
  services,
  // Preference order; flat is always the fallback. Enable "still-fal" with FAL_KEY set.
  renderers: ["flat"],
});
