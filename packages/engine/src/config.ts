// videotape.config.ts (spec §11).

import type { App, CutRenderer, SceneRenderer, Services } from "@videotape/core";

export interface Budgets {
  /** First render of a session before the flat fallback is sent (spec §7.5). */
  firstRenderMs: number;
  /** Click → next frame before the flat fallback is sent. */
  transitionMs: number;
  /** Crossfade length when no generated cut is ready. */
  crossfadeMs: number;
}

export const DEFAULT_BUDGETS: Budgets = { firstRenderMs: 1500, transitionMs: 300, crossfadeMs: 400 };

export interface VideotapeConfig {
  app: App;
  services?: Services;
  /**
   * Scene renderers in order of preference, as instances or ids the CLI knows
   * (`flat`, `still-fal`). `flat` is always appended as the final fallback.
   */
  renderers?: Array<SceneRenderer | string>;
  /** Options per renderer id, passed to the renderer's factory by the CLI. */
  rendererOptions?: Record<string, Record<string, unknown>>;
  cuts?: CutRenderer[];
  /** Cache directory, relative to the app. Default `.videotape/cache`. */
  cache?: string;
  /** App assets served at `/app/`, relative to the app. Default `public`. */
  publicDir?: string;
  budgets?: Partial<Budgets>;
  /** Allow `reroll` messages and attach HUD details to renders. Default: on in dev, off in serve. */
  debug?: boolean;
}

export function defineConfig(config: VideotapeConfig): VideotapeConfig {
  return config;
}
