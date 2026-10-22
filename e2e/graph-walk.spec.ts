// S5: walk every edge of the demo graph in a real browser, with the flat renderer.
import { expect, test } from "@playwright/test";
import { checkStay, edgeName, expectHead, graph, open, pathTo, take } from "./helpers";

test("the graph has edges to walk", () => {
  expect(graph.edges.length).toBeGreaterThan(10);
});

for (const edge of graph.edges) {
  test(edgeName(edge), async ({ page }) => {
    await open(page);
    // History as the engine keeps it: jump pushes, goto does not, back pops.
    const history: string[] = [];
    let at = graph.entry;
    for (const step of pathTo(edge.from)) {
      await take(page, step);
      if (step.kind === "jump") history.push(at);
      at = step.to!;
      await expectHead(page, at);
    }

    await take(page, edge);
    if (edge.kind === "back") {
      await expectHead(page, history.at(-1)!);
    } else if (edge.kind === "stay") {
      await checkStay(page, edge);
      await expectHead(page, at);
    } else {
      await expectHead(page, edge.to!);
    }
  });
}
