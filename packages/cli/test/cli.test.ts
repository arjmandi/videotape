import { afterEach, describe, expect, it, vi } from "vitest";
import { main } from "../src/main";

const fixture = (name: string) => new URL(`./fixtures/${name}`, import.meta.url).pathname;

function capture() {
  let out = "";
  const spy = vi.spyOn(process.stdout, "write").mockImplementation((chunk: string | Uint8Array) => {
    out += String(chunk);
    return true;
  });
  return { text: () => out, spy };
}

afterEach(() => vi.restoreAllMocks());

describe("videotape check", () => {
  it("exits 0 and says so for a clean app", async () => {
    const c = capture();
    expect(await main(["check", fixture("clean")])).toBe(0);
    expect(c.text()).toContain("2 tapes, 2 frames: no problems");
  });

  it("exits 1 and lists each problem with its code and location", async () => {
    const c = capture();
    expect(await main(["check", fixture("broken")])).toBe(1);
    const out = c.text();
    expect(out).toMatch(/error\s+no-action\s+home\/main#go/);
    expect(out).toMatch(/error\s+unknown-tape\s+home\/main#away/);
    expect(out).toContain("2 errors, 1 warning");
  });
});

describe("videotape graph", () => {
  it("prints Mermaid by default and JSON on request", async () => {
    let c = capture();
    expect(await main(["graph", fixture("clean")])).toBe(0);
    expect(c.text()).toContain('a_one -->|"next·press"| b_two');
    vi.restoreAllMocks();
    c = capture();
    expect(await main(["graph", fixture("clean"), "--format", "json"])).toBe(0);
    expect(JSON.parse(c.text()).entry).toBe("a/one");
  });
});

describe("videotape (no command)", () => {
  it("prints help", async () => {
    const c = capture();
    expect(await main([])).toBe(0);
    expect(c.text()).toContain("Usage: videotape <command>");
  });
});
