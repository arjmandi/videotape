"""The journey graph: frames are nodes, outcomes are edges (05 §6.3).

`reachable`, `has_exit`, `components` (Tarjan), and `closed_cycles` are ported from prototype-0's
`packages/core/src/graph.ts`. `back` and `done` leave a frame for a place decided by history, so
they count as exits but add no node.

`journey` adds what the engine does without being told (Q31, Q32): every frame with history has
the platform's back, except history roots (the app's entry, each hub destination's first frame,
and wherever an outcome that signs in or out lands) and frames with `back=False`; and a frame
shows the hub's doors when every root its history can begin at is a hub destination.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .intent import App

EXITS = ("back", "done")
KEEPS_HISTORY = ("goto", "jump")
"""Edges along which a history grows; a call's sheet, the hub, and sign-in or sign-out do not."""


@dataclass(frozen=True)
class Edge:
    """An edge of the journey graph, from a frame, by an action or an outcome a handler returns."""

    source: str
    type: str
    via: dict[str, Any]
    target: str | None = None
    """The tape (jump, call, hub) or frame (goto) the outcome names."""
    to: str | None = None
    """The frame it reaches, when known statically: absent for back and done, and for unknown names."""
    resets: bool = False
    """The outcome signs in or out, so history starts again at its target (Q31)."""

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"from": self.source}
        if self.to:
            out["to"] = self.to
        out["type"] = self.type
        if self.target is not None:
            out["tape" if self.type in ("jump", "call", "hub") else "frame"] = self.target
        if self.resets:
            out["resets_history"] = True
        out["via"] = self.via
        return out


@dataclass(frozen=True)
class Graph:
    entry: str | None
    nodes: list[str]
    edges: list[Edge]

    def out(self, node: str) -> list[Edge]:
        return [e for e in self.edges if e.source == node]


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


# ── history and the hub ──────────────────────────────────────────────────────


@dataclass
class Journey:
    """The declared graph, and what history and the hub add to it."""

    entry: str | None
    nodes: list[str]
    declared: list[Edge]
    roots: set[str] = field(default_factory=set)
    """History roots: no back (Q31)."""
    always: set[str] = field(default_factory=set)
    """Roots on every path: nothing enters them with history (Q44). The rest are roots on some paths."""
    backs: list[Edge] = field(default_factory=list)
    """The platform's back, from every frame with history that does not opt out."""
    doors: list[Edge] = field(default_factory=list)
    """The hub's doors, from every frame that shows the hub (Q32)."""
    began: dict[str, set[str]] = field(default_factory=dict)
    """For each frame, the roots its history can begin at."""

    @property
    def sometimes(self) -> set[str]:
        return self.roots - self.always

    @property
    def graph(self) -> Graph:
        """Declared edges, the platform's back, and the hub's doors. An explicit back from a frame that is
        a root on every path has nowhere to go, so it is no exit (Q44)."""
        declared = [e for e in self.declared if not (e.type == "back" and e.source in self.always)]
        return Graph(self.entry, self.nodes, [*declared, *self.backs, *self.doors])


def _walk(starts: set[str], edges: list[Edge], stop: set[str]) -> dict[str, set[str]]:
    """For each node, the starts it can be reached from along `edges`, not passing into `stop`."""
    out: dict[str, set[str]] = {}
    for s in sorted(starts):
        queue, seen = deque([s]), {s}
        while queue:
            n = queue.popleft()
            out.setdefault(n, set()).add(s)
            for e in edges:
                if e.source == n and e.to and e.to not in seen and e.to not in stop:
                    seen.add(e.to)
                    queue.append(e.to)
    return out


def journey(app: App, edges: list[Edge]) -> Journey:
    tape = app.tape(app.entry)
    entry = tape.entry.node if tape else None
    frames = {f.node: f for f in app.frames}
    nodes = list(frames)
    destinations = {}
    if app.hub is not None:
        for d in app.hub.destinations:
            t = app.tape(d.tape)
            if t is not None:
                destinations[d.tape] = t.entry.node
    roots = {n for n in [entry, *destinations.values()] if n} | {e.to for e in edges if e.resets and e.to}
    j = Journey(entry, nodes, edges, roots)
    entered_with_history = {e.to for e in edges if e.to and e.type in ("goto", "jump", "call") and not e.resets}
    j.always = {r for r in roots if r not in entered_with_history}
    j.backs = [Edge(n, "back", {"back": "history"}) for n in nodes if n not in roots and frames[n].back]
    keeps = [e for e in edges if e.type in KEEPS_HISTORY and not e.resets]
    j.began = _walk(roots, keeps, roots)
    called = set(_walk({e.to for e in edges if e.type == "call" and e.to}, keeps, roots))
    homes = set(destinations.values())
    for n in nodes:
        began = j.began.get(n, set())
        if app.hub is not None and frames[n].hub and n not in called and began and began <= homes:
            j.doors.extend(Edge(n, "hub", {"hub": t}, t, node) for t, node in destinations.items())
    return j
