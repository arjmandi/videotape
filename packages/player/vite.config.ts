import { defineConfig } from "vite";

export default defineConfig({
  root: __dirname,
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2022",
    // No inline scripts: the player CSP forbids them (spec §10).
    modulePreload: { polyfill: false },
    assetsInlineLimit: 0,
  },
  server: {
    proxy: {
      "/vtp": { target: "ws://127.0.0.1:4173", ws: true },
      "/a": "http://127.0.0.1:4173",
      "/app": "http://127.0.0.1:4173",
    },
  },
});
