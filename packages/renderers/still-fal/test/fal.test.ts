import { afterEach, describe, expect, it, vi } from "vitest";
import { type SceneRequest, dusk, frame, layout, text } from "@videotape/core";
import { DEFAULT_MODEL, FalError, falStill } from "../src";

const wf = layout(frame("f", { layout: "hero", components: [text("t", "Title")] }), "desktop", dusk);
const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 1, 2, 3]);

const request = (over: Partial<SceneRequest> = {}): SceneRequest => ({
  key: "sha256:k", canvas: wf.canvas, seed: 4210, prompt: "Cinematic UI backdrop, dusk, no text",
  condition: { svg: wf.svg, png: PNG }, masks: { reserved: new Uint8Array(), surface: new Uint8Array() }, style: dusk, wireframe: wf,
  ...over,
});

type Call = { url: string; init: RequestInit | undefined };

function fakeFetch(...responses: Array<Response | ((call: Call) => Response)>) {
  const calls: Call[] = [];
  const fn = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const call = { url: String(url), init };
    calls.push(call);
    if (init?.signal?.aborted) throw init.signal.reason ?? new Error("aborted");
    const next = responses.shift();
    if (!next) throw new Error("unexpected fetch");
    return typeof next === "function" ? next(call) : next;
  });
  return { fn: fn as unknown as typeof fetch, calls };
}

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
const inline = { images: [{ url: `data:image/png;base64,${Buffer.from([9, 8, 7]).toString("base64")}`, content_type: "image/png" }], seed: 4210 };

afterEach(() => vi.unstubAllEnvs());

describe("fal still renderer", () => {
  it("posts the wireframe, prompt, seed, and strength to the model with the key from the environment", async () => {
    vi.stubEnv("FAL_KEY", "test-key-123");
    const f = fakeFetch(ok(inline));
    const asset = await falStill({ fetch: f.fn }).render(request(), new AbortController().signal);

    expect(f.calls[0]!.url).toBe(`https://fal.run/${DEFAULT_MODEL}`);
    const headers = f.calls[0]!.init!.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Key test-key-123");
    const body = JSON.parse(String(f.calls[0]!.init!.body));
    expect(body).toMatchObject({
      prompt: "Cinematic UI backdrop, dusk, no text", seed: 4210, strength: 0.82, sync_mode: true, output_format: "png", num_images: 1,
    });
    expect(body.image_url).toBe(`data:image/png;base64,${Buffer.from(PNG).toString("base64")}`);
    expect([...asset.bytes]).toEqual([9, 8, 7]);
    expect(asset).toMatchObject({ key: "sha256:k", mime: "image/png", meta: { model: DEFAULT_MODEL, seed: 4210 } });
  });

  it("downloads the image when fal returns a URL instead of inline data", async () => {
    vi.stubEnv("FAL_KEY", "k");
    const f = fakeFetch(
      ok({ images: [{ url: "https://v3.fal.media/files/x.jpg", content_type: "image/jpeg" }] }),
      new Response(new Uint8Array([1, 1, 2]), { headers: { "content-type": "image/jpeg" } }),
    );
    const asset = await falStill({ fetch: f.fn }).render(request(), new AbortController().signal);
    expect(f.calls[1]!.url).toBe("https://v3.fal.media/files/x.jpg");
    expect(asset.mime).toBe("image/jpeg");
    expect([...asset.bytes]).toEqual([1, 1, 2]);
  });

  it("uses the configured model and puts it in the renderer version, so cache keys change with it", () => {
    const a = falStill({ model: "fal-ai/other/model", strength: 0.6, key: "k" });
    expect(a.version).toContain("fal-ai/other/model");
    expect(a.version).not.toBe(falStill({ key: "k" }).version);
  });

  it("turns a non-2xx answer into a typed error with the status", async () => {
    vi.stubEnv("FAL_KEY", "k");
    const f = fakeFetch(new Response("quota exceeded", { status: 429 }));
    const err = await falStill({ fetch: f.fn }).render(request(), new AbortController().signal).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(FalError);
    expect(err).toMatchObject({ status: 429 });
    expect(String((err as Error).message)).toContain("quota exceeded");
  });

  it("refuses an image the safety checker flagged", async () => {
    vi.stubEnv("FAL_KEY", "k");
    const f = fakeFetch(ok({ ...inline, has_nsfw_concepts: [true] }));
    await expect(falStill({ fetch: f.fn }).render(request(), new AbortController().signal)).rejects.toThrow(/flagged/);
  });

  it("passes the abort signal through", async () => {
    vi.stubEnv("FAL_KEY", "k");
    const ac = new AbortController();
    ac.abort(new Error("budget spent"));
    const f = fakeFetch(ok(inline));
    await expect(falStill({ fetch: f.fn }).render(request(), ac.signal)).rejects.toThrow("budget spent");
    expect(f.calls[0]!.init!.signal).toBe(ac.signal);
  });

  it("reports itself unavailable with no key, so the engine uses flat", async () => {
    vi.stubEnv("FAL_KEY", "");
    const r = falStill({ fetch: fakeFetch().fn });
    expect(r.available!()).toBe(false);
    await expect(r.render(request(), new AbortController().signal)).rejects.toMatchObject({ status: 401 });
  });

  it("never sends reel data: the body holds only the prompt, the wireframe, and generation settings", async () => {
    vi.stubEnv("FAL_KEY", "k");
    const f = fakeFetch(ok(inline));
    await falStill({ fetch: f.fn }).render(request(), new AbortController().signal);
    expect(Object.keys(JSON.parse(String(f.calls[0]!.init!.body))).sort()).toEqual([
      "enable_safety_checker", "guidance_scale", "image_url", "num_images", "num_inference_steps", "output_format", "prompt", "seed", "strength", "sync_mode",
    ]);
  });
});
