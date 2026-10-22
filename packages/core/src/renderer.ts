// Renderer plugin interface (spec §7.6). Types only: renderer packages depend
// on core, and the engine hosts them without knowing which model is in use.

import type { Wireframe } from "./layout";
import type { StylePack } from "./style";
import type { Size } from "./viewport";

export interface SceneRequest {
  key: string;
  canvas: Size;
  seed: number;
  prompt: string;
  negative?: string;
  /** The scene drawing as conditioning: SVG source and a PNG raster at canvas size. */
  condition: { svg: string; png: Uint8Array };
  /** Grayscale PNG masks at canvas size: white where the mask applies. */
  masks: { reserved: Uint8Array; surface: Uint8Array };
  style: StylePack;
  wireframe: Wireframe;
  /**
   * How far the generator may move away from the conditioning image, 0–1. Set by the
   * engine only when the drawing gives little to build on; otherwise the renderer's own
   * default applies. Renderers map it to their parameter (image-to-image strength, denoise).
   */
  freedom?: number;
}

export interface CutRequest {
  key: string;
  canvas: Size;
  seed: number;
  from: SceneAsset;
  to: SceneAsset;
  prompt: string;
  durationMs: number;
}

export interface SceneAsset {
  key: string;
  mime: "image/webp" | "image/png" | "image/jpeg";
  bytes: Uint8Array;
  meta: Record<string, unknown>;
}

export interface CutAsset {
  key: string;
  mime: "video/webm" | "video/mp4";
  bytes: Uint8Array;
  durationMs: number;
  meta: Record<string, unknown>;
}

export interface SceneRenderer {
  id: string;
  version: string;
  kind: "scene";
  /** True for deterministic renderers that need no validation (the flat renderer). */
  deterministic?: boolean;
  /** False when the backend cannot be used (for example, a missing API key). */
  available?(): boolean;
  render(req: SceneRequest, signal: AbortSignal): Promise<SceneAsset>;
}

export interface CutRenderer {
  id: string;
  version: string;
  kind: "cut";
  available?(): boolean;
  render(req: CutRequest, signal: AbortSignal): Promise<CutAsset>;
}

/** v1: interface only (spec N1). */
export interface LiveRenderer {
  id: string;
  version: string;
  kind: "live";
  open(session: unknown): unknown;
}
