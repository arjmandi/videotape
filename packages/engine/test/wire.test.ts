import { afterAll, beforeAll, describe, expect, it } from "vitest";
import WebSocket from "ws";
import type { RenderMessage, ServerMessage } from "@videotape/core";
import demo from "../../../apps/site/tapes";
import { services } from "../../../apps/site/services";
import { Engine, MemoryCache, type RunningServer, memoryLogger, startServer } from "../src";

let server: RunningServer;

beforeAll(async () => {
  const engine = new Engine({ app: demo, services }, { cache: new MemoryCache(), logger: memoryLogger() });
  server = await startServer({ engine, port: 0 });
});
afterAll(() => server.close());

/** A minimal VTP client over a real socket. */
async function client(origin?: string) {
  const ws = new WebSocket(server.url.replace("http", "ws") + "/vtp", origin ? { origin } : {});
  const inbox: ServerMessage[] = [];
  const waiters: Array<() => void> = [];
  ws.on("message", (d) => {
    inbox.push(JSON.parse(String(d)));
    waiters.splice(0).forEach((w) => w());
  });
  await new Promise((r, j) => { ws.once("open", r); ws.once("error", j); });
  let seq = 0;
  const until = async (pred: (m: ServerMessage) => boolean): Promise<ServerMessage> => {
    for (;;) {
      const hit = inbox.find(pred);
      if (hit) {
        inbox.splice(inbox.indexOf(hit), 1);
        return hit;
      }
      await new Promise<void>((r) => waiters.push(r));
    }
  };
  let last: RenderMessage | undefined;
  const nextRender = async () => (last = (await until((m) => m.t === "render")) as RenderMessage);
  return {
    ws,
    hello: () => ws.send(JSON.stringify({ t: "hello", v: 1, viewport: { w: 1440, h: 900, dpr: 2 }, caps: { video: ["webm"], webrtc: false } })),
    press: (component: string, values?: Record<string, string>) =>
      ws.send(JSON.stringify({ t: "event", seq: ++seq, render: last!.seq, component, type: "press", ...(values ? { values } : {}) })),
    until,
    nextRender,
    close: () => ws.close(),
  };
}

describe("VTP over a real WebSocket", () => {
  it("walks landing → login (wrong, then right) → dashboard → report → back", async () => {
    const c = await client();
    c.hello();
    expect(await c.until((m) => m.t === "welcome")).toMatchObject({ viewportClass: "desktop" });
    expect((await c.nextRender()).head).toEqual({ tape: "landing", frame: "home" });

    c.press("signin");
    expect((await c.nextRender()).head).toEqual({ tape: "login", frame: "form" });

    c.press("submit", { username: "ada", password: "nope" });
    const patch = await c.until((m) => m.t === "patch" && !!m.content?.length);
    expect(patch).toMatchObject({ content: [{ id: "error", value: "Wrong credentials" }] });

    c.press("submit", { username: "ada", password: "lovelace" });
    expect((await c.nextRender()).head).toEqual({ tape: "dashboard", frame: "home" });
    c.press("report");
    expect((await c.nextRender()).head).toEqual({ tape: "report", frame: "view" });
    c.press("backlink");
    expect((await c.nextRender()).head).toEqual({ tape: "dashboard", frame: "home" });
    c.close();
  });

  it("serves scene assets immutable, typed, and byte-identical across sessions", async () => {
    const a = await client();
    a.hello();
    const ra = await a.nextRender();
    const b = await client();
    b.hello();
    const rb = await b.nextRender();
    expect(rb.layers[0]!.url).toBe(ra.layers[0]!.url);

    const res = await fetch(server.url + ra.layers[0]!.url);
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("public, max-age=31536000, immutable");
    expect(res.headers.get("content-type")).toBe("image/png");
    const one = Buffer.from(await res.arrayBuffer());
    const two = Buffer.from(await (await fetch(server.url + rb.layers[0]!.url)).arrayBuffer());
    expect(one.equals(two)).toBe(true);
    a.close();
    b.close();
  });

  it("refuses asset paths that are not content hashes", async () => {
    for (const path of ["/a/..%2F..%2Fpackage.json", "/a/abc.png", "/app/..%2F..%2Fpackage.json"]) {
      expect((await fetch(server.url + path)).status, path).toBe(404);
    }
  });

  it("closes a socket opened from another origin", async () => {
    const c = await client("https://evil.example");
    const code = await new Promise<number>((r) => c.ws.once("close", (code) => r(code)));
    expect(code).toBe(1008);
  });

  it("reports health", async () => {
    expect(await (await fetch(server.url + "/healthz")).json()).toMatchObject({ ok: true });
  });
});
