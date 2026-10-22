import { describe, expect, it } from "vitest";
import { ClientMessageSchema, MAX_VALUE_BYTES, ServerMessageSchema, decode } from "../src";

// Spec Appendix B, with the amendments in §9 (welcome.token, event.render).
const appendixB = {
  hello: { t: "hello", v: 1, viewport: { w: 1440, h: 900, dpr: 2 }, caps: { video: ["webm", "mp4"], webrtc: true } },
  welcome: {
    t: "welcome", session: "s_8f2", token: "tok", viewportClass: "desktop", canvas: { w: 1920, h: 1080 },
    style: { id: "dusk", palette: { bg: "#14121a", fg: "#f3ede4", accent: "#ff6a3d", muted: "#8a8494" },
      fonts: { display: "Instrument Serif", body: "Inter" } },
  },
  render: {
    t: "render", seq: 1, head: { tape: "login", frame: "form" }, key: "sha256:abc",
    layers: [{ kind: "image", url: "/a/3c9e.webp", z: 0 }],
    regions: [{ id: "username", kind: "input", rect: [0.35, 0.42, 0.3, 0.06], mask: "reserved" }],
    content: [
      { id: "title", kind: "text", variant: "title", value: "Welcome back", rect: [0.35, 0.28, 0.3, 0.08] },
      { id: "username", kind: "input", inputType: "text", label: "Username", rect: [0.35, 0.42, 0.3, 0.06] },
      { id: "password", kind: "input", inputType: "secret", label: "Password", rect: [0.35, 0.5, 0.3, 0.06] },
      { id: "submit", kind: "button", label: "Sign in", emphasis: "primary", rect: [0.35, 0.6, 0.3, 0.06] },
    ],
    edges: [
      { component: "submit", event: "press", kind: "jump", to: { tape: "dashboard", frame: "home" }, cut: "/a/77ab.webm" },
      { component: "forgot", event: "press", kind: "jump", to: { tape: "reset", frame: "ask" } },
    ],
    a11y: { title: "Sign in" }, fallback: false,
  },
  event: { t: "event", seq: 1, render: 1, component: "submit", type: "press", values: { username: "ada", password: "••••" } },
  cut: { t: "cut", seq: 2, from: "sha256:a", to: "sha256:b", url: "/a/77ab.webm", durationMs: 900, kind: "generated" },
};

describe("VTP schemas", () => {
  it("accept every Appendix B message", () => {
    for (const m of [appendixB.hello, appendixB.event]) expect(ClientMessageSchema.safeParse(m).success, m.t).toBe(true);
    for (const m of [appendixB.welcome, appendixB.render, appendixB.cut]) expect(ServerMessageSchema.safeParse(m).success, m.t).toBe(true);
  });

  it("accept a crossfade cut with no url", () => {
    const { url: _, ...crossfade } = appendixB.cut;
    expect(ServerMessageSchema.safeParse({ ...crossfade, kind: "crossfade" }).success).toBe(true);
  });

  const rejected: Array<[string, unknown]> = [
    ["no t", { v: 1 }],
    ["wrong version", { ...appendixB.hello, v: 2 }],
    ["negative seq", { ...appendixB.event, seq: -1 }],
    ["missing render guard", { ...appendixB.event, render: undefined }],
    ["value over 4 KB", { ...appendixB.event, value: "x".repeat(MAX_VALUE_BYTES + 1) }],
    ["object value", { ...appendixB.event, value: { nested: true } }],
    ["huge viewport", { ...appendixB.hello, viewport: { w: 1e9, h: 1, dpr: 1 } }],
    ["unknown message", { t: "shutdown" }],
  ];
  it.each(rejected)("reject a client message with %s", (_name, m) => {
    expect(ClientMessageSchema.safeParse(m).success).toBe(false);
  });

  it("reject a render with an unknown component kind", () => {
    const bad = { ...appendixB.render, content: [{ id: "x", kind: "iframe", rect: [0, 0, 1, 1] }] };
    expect(ServerMessageSchema.safeParse(bad).success).toBe(false);
  });

  it("decode reports non-JSON, oversized, and invalid input", () => {
    expect(decode(ClientMessageSchema, "{").ok).toBe(false);
    expect(decode(ClientMessageSchema, " ".repeat(300_000)).ok).toBe(false);
    const r = decode(ClientMessageSchema, JSON.stringify({ t: "ping" }));
    expect(r).toEqual({ ok: true, msg: { t: "ping" } });
  });
});
