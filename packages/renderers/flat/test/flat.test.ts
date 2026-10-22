import { describe, expect, it } from "vitest";
import { type SceneRequest, button, dusk, frame, layout, text } from "@videotape/core";
import { flatRenderer, rasterize } from "../src";

const f = frame("f", { layout: "hero", components: [text("t", "Title"), button("b", "Go", { on: { press: "x" } })] });

function request(cls: "phone" | "desktop"): SceneRequest {
  const wf = layout(f, cls, dusk);
  return {
    key: "k", canvas: wf.canvas, seed: 1, prompt: "", style: dusk, wireframe: wf,
    condition: { svg: wf.svg, png: new Uint8Array() }, masks: { reserved: new Uint8Array(), surface: new Uint8Array() },
  };
}

/** Width and height from a PNG's IHDR chunk. */
function pngSize(bytes: Uint8Array): [number, number] {
  const v = new DataView(bytes.buffer, bytes.byteOffset);
  return [v.getUint32(16), v.getUint32(20)];
}

describe("flat renderer", () => {
  it("renders a PNG at the canonical canvas size", async () => {
    const a = await flatRenderer().render(request("desktop"), new AbortController().signal);
    expect(a.mime).toBe("image/png");
    expect([...a.bytes.slice(1, 4)].map((c) => String.fromCharCode(c)).join("")).toBe("PNG");
    expect(pngSize(a.bytes)).toEqual([1920, 1080]);
    expect(pngSize((await flatRenderer().render(request("phone"), new AbortController().signal)).bytes)).toEqual([1080, 1920]);
  });

  it("is byte-identical for the same request (S3)", async () => {
    const r = flatRenderer();
    const a = await r.render(request("desktop"), new AbortController().signal);
    const b = await r.render(request("desktop"), new AbortController().signal);
    expect(Buffer.from(a.bytes).equals(Buffer.from(b.bytes))).toBe(true);
  });

  it("honours an aborted signal", async () => {
    const ac = new AbortController();
    ac.abort();
    await expect(flatRenderer().render(request("desktop"), ac.signal)).rejects.toThrow();
  });

  it("rasterises at a requested width", () => {
    const png = rasterize('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50"><rect width="100" height="50" fill="#fff"/></svg>', 200);
    expect(pngSize(png)).toEqual([200, 100]);
  });
});
