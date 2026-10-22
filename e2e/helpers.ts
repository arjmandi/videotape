import { execFileSync } from "node:child_process";
import { type Page, expect } from "@playwright/test";

export interface GraphEdge {
  from: string;
  component: string;
  event: string;
  handler?: string;
  kind: "goto" | "jump" | "back" | "stay";
  to?: string;
}
export interface Graph {
  entry: string;
  nodes: string[];
  edges: GraphEdge[];
}

/** The demo's journey graph, from the same CLI a developer runs. */
export const graph: Graph = JSON.parse(
  execFileSync(process.execPath, ["packages/cli/bin/videotape.mjs", "graph", "apps/site", "--format", "json"], { encoding: "utf8" }),
);

export const edgeName = (e: GraphEdge) => `${e.from} ${e.component}·${e.event}${e.handler ? ` ⇒ ${e.handler}` : ""} → ${e.to ?? e.kind}`;

const player = (page: Page) => page.locator(".vt");

export async function expectHead(page: Page, node: string): Promise<void> {
  await expect(player(page)).toHaveAttribute("data-vt-head", node);
  await expect(player(page)).toHaveAttribute("data-vt-state", "ready");
}

export async function open(page: Page): Promise<void> {
  await page.goto("/");
  await expectHead(page, graph.entry);
}

const node = (page: Page, id: string) => page.locator(`.vt-content [data-vt-id="${id}"]`);

export async function signIn(page: Page, password = "lovelace"): Promise<void> {
  await page.getByLabel("Username").fill("ada");
  await page.getByLabel("Password").fill(password);
  await node(page, "submit").click();
}

/**
 * How to take each handler edge, and what proves it happened. Static edges need
 * no fixture: pressing the component is enough.
 */
const FIXTURES: Record<string, { take(page: Page): Promise<void>; check?(page: Page): Promise<void> }> = {
  "login/form#submit→dashboard/home": { take: (p) => signIn(p) },
  "login/form#submit→stay": {
    take: (p) => signIn(p, "wrong"),
    check: (p) => expect(node(p, "error")).toHaveText("Wrong credentials"),
  },
  "docs/read#toc→stay": {
    take: (p) => node(p, "toc").getByRole("button", { name: "Layout owns space" }).click(),
    check: (p) => expect(node(p, "title")).toHaveText("Layout owns space"),
  },
  "report/view#export→stay": {
    take: (p) => node(p, "export").click(),
    check: (p) => expect(node(p, "exported")).toHaveText("Exported 30 rows as views-30d.csv"),
  },
};

const fixtureKey = (e: GraphEdge) => `${e.from}#${e.component}→${e.kind === "stay" ? "stay" : e.to}`;

export async function take(page: Page, e: GraphEdge): Promise<void> {
  const f = e.handler ? FIXTURES[fixtureKey(e)] : undefined;
  if (e.handler && !f) throw new Error(`no fixture for handler edge ${fixtureKey(e)}`);
  if (f) await f.take(page);
  else if (e.event === "select") await node(page, e.component).getByRole("button").first().click();
  else await node(page, e.component).click();
}

export async function checkStay(page: Page, e: GraphEdge): Promise<void> {
  await FIXTURES[fixtureKey(e)]?.check?.(page);
}

/** Shortest path of forward edges from the entry to `target`. */
export function pathTo(target: string): GraphEdge[] {
  const prev = new Map<string, GraphEdge | null>([[graph.entry, null]]);
  const queue = [graph.entry];
  while (queue.length) {
    const n = queue.shift()!;
    if (n === target) break;
    for (const e of graph.edges) {
      if (e.from === n && e.to && e.kind !== "stay" && !prev.has(e.to)) {
        prev.set(e.to, e);
        queue.push(e.to);
      }
    }
  }
  if (!prev.has(target)) throw new Error(`${target} is unreachable`);
  const path: GraphEdge[] = [];
  for (let e = prev.get(target); e; e = prev.get(e.from)) path.unshift(e);
  return path;
}
