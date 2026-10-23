"""The journey graph: frames are nodes, outcomes are edges (05 §6.3).

Ported from prototype-0's `packages/core/src/graph.ts`: `reachable`, `has_exit`, `components`
(Tarjan), and `closed_cycles`. `back` and `done` leave a frame for a place decided by history, so
they count as exits but add no node.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .intent import App
from .serialize import Edge

EXITS = ("back", "done")


@dataclass(frozen=True)
class Graph:
    entry: str | None
    nodes: list[str]
    edges: list[Edge]

    def out(self, node: str) -> list[Edge]:
        return [e for e in self.edges if e.source == node]


def graph(app: App, edges: list[Edge]) -> Graph:
    tape = app.tape(app.entry)
    return Graph(tape.entry.node if tape else None, [f.node for f in app.frames], edges)


def reachable(g: Graph) -> set[str]:
    """Nodes reachable from the entry. `back` only returns to visited nodes, so it adds none."""
    seen: set[str] = set()
    if g.entry is None:
        return seen
    queue = deque([g.entry])
    while queue:
        n = queue.popleft()
        if n in seen:
            continue
        seen.add(n)
        queue.extend(e.to for e in g.out(n) if e.to and e.to not in seen)
    return seen


def has_exit(g: Graph, n: str) -> bool:
    """True when a node has any edge that can take the journey elsewhere."""
    return any(e.type in EXITS or (e.to is not None and e.to != n) for e in g.out(n))


def components(g: Graph) -> list[list[str]]:
    """Strongly connected components (Tarjan), over static edges."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    out: list[list[str]] = []

    def visit(v: str) -> None:
        index[v] = low[v] = len(index)
        stack.append(v)
        on_stack.add(v)
        for w in [e.to for e in g.out(v) if e.to]:
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                scc.append(w)
                if w == v:
                    break
            out.append(scc)

    for n in g.nodes:
        if n not in index:
            visit(n)
    return out


def closed_cycles(g: Graph) -> list[list[str]]:
    """Cycles the journey can enter but never leave: a terminal component of more than one frame.

    The component that holds the entry is left out: when it is terminal, it is the whole
    reachable app, which is no trap (an app whose frames all reach each other, as with a hub).
    """
    out = []
    for scc in components(g):
        inside = set(scc)
        if len(scc) < 2 or g.entry in inside:
            continue
        leaves = any(e.type in EXITS or (e.to is not None and e.to not in inside) for n in scc for e in g.out(n))
        if not leaves:
            out.append([n for n in g.nodes if n in inside])
    return out
