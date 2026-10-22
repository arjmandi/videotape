// Layout-conditioned scene generation on fal.ai (spec §7.7, `still`).
//
// Image-to-image over the wireframe raster: the conditioning image fixes where
// panels, fields, and buttons are, and `strength` decides how far the model may
// move from it. Plain HTTP; no vendor SDK. Model ids change, so the model is
// configurable and part of the renderer version (and so of every cache key).

import type { SceneAsset, SceneRenderer, SceneRequest } from "@videotape/core";

export const DEFAULT_MODEL = "fal-ai/flux/dev/image-to-image";

export interface FalStillOptions {
  /** fal endpoint id. Default: FLUX.1 [dev] image-to-image. */
  model?: string;
  /** How far the model may move from the wireframe, 0.01–1. Default 0.82. */
  strength?: number;
  steps?: number;
  guidance?: number;
  /** API key; default `FAL_KEY` from the environment. Never read from config files (spec §11). */
  key?: string;
  baseUrl?: string;
  fetch?: typeof fetch;
}

export class FalError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
    this.name = "FalError";
  }
}

function base64(bytes: Uint8Array): string {
  return Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength).toString("base64");
}

function fromDataUri(uri: string): { bytes: Uint8Array; mime: string } {
  const m = /^data:([^;,]+)(;base64)?,(.*)$/s.exec(uri);
  if (!m) throw new FalError(0, "fal returned an unreadable data URI");
  const bytes = m[2] ? Buffer.from(m[3]!, "base64") : Buffer.from(decodeURIComponent(m[3]!));
  return { bytes: new Uint8Array(bytes), mime: m[1]! };
}

const MIMES: Record<string, SceneAsset["mime"]> = { "image/png": "image/png", "image/jpeg": "image/jpeg", "image/webp": "image/webp" };

interface FalResponse {
  images?: Array<{ url?: string; content_type?: string }>;
  seed?: number;
  has_nsfw_concepts?: boolean[];
}

export function falStill(opts: FalStillOptions = {}): SceneRenderer {
  const model = opts.model ?? DEFAULT_MODEL;
  const strength = opts.strength ?? 0.82;
  const steps = opts.steps ?? 28;
  const guidance = opts.guidance ?? 3.5;
  const key = () => opts.key ?? process.env.FAL_KEY;
  const http = opts.fetch ?? fetch;
  const baseUrl = (opts.baseUrl ?? "https://fal.run").replace(/\/$/, "");

  return {
    id: "still-fal",
    version: `1:${model}:s${strength}:n${steps}:g${guidance}`,
    kind: "scene",
    available: () => !!key(),
    async render(req: SceneRequest, signal: AbortSignal): Promise<SceneAsset> {
      const k = key();
      if (!k) throw new FalError(401, "FAL_KEY is not set");
      if (req.condition.png.byteLength === 0) throw new FalError(0, "the request has no conditioning image");
      const res = await http(`${baseUrl}/${model}`, {
        method: "POST",
        headers: { Authorization: `Key ${k}`, "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          prompt: req.prompt,
          image_url: `data:image/png;base64,${base64(req.condition.png)}`,
          strength,
          seed: req.seed,
          num_inference_steps: steps,
          guidance_scale: guidance,
          num_images: 1,
          output_format: "png",
          // Return the image inline: one round trip, and nothing left in fal's request history.
          sync_mode: true,
          enable_safety_checker: true,
        }),
        signal,
      });
      if (!res.ok) {
        const detail = (await res.text().catch(() => "")).slice(0, 300);
        throw new FalError(res.status, `fal ${model} answered ${res.status}${detail ? `: ${detail}` : ""}`);
      }
      const json = (await res.json()) as FalResponse;
      const image = json.images?.[0];
      if (!image?.url) throw new FalError(res.status, `fal ${model} returned no image`);
      if (json.has_nsfw_concepts?.[0]) throw new FalError(res.status, "fal flagged the scene; it will not be used");

      let bytes: Uint8Array;
      let mime: string;
      if (image.url.startsWith("data:")) {
        ({ bytes, mime } = fromDataUri(image.url));
      } else {
        const img = await http(image.url, { signal });
        if (!img.ok) throw new FalError(img.status, `could not download the scene (${img.status})`);
        bytes = new Uint8Array(await img.arrayBuffer());
        mime = image.content_type ?? img.headers.get("content-type") ?? "image/png";
      }
      return {
        key: req.key,
        mime: MIMES[mime.split(";")[0]!.trim()] ?? "image/png",
        bytes,
        meta: { renderer: "still-fal", model, seed: json.seed ?? req.seed, strength },
      };
    },
  };
}
