"""The journey graph: frames are nodes, outcomes are edges (05 §6.3).

`reachable`, `has_exit`, `components` (Tarjan), and `closed_cycles` are ported from prototype-0's
`packages/core/src/graph.ts`. `back` and `done` leave a frame for a place decided by history, so
they count as exits but add no node.

`journey` adds what the engine does without being told (Q31, Q32, Q48, Q49). History roots are the
app's entry, each hub destination's first frame, wherever an outcome that signs in or out lands,
and a frame opened by its address when no hub destination reaches it (with a hub, the first
destination in hub order that reaches it is put beneath it instead). Back is a way out only where
a frame has history on every path to it: never on a root, even one that is a root on some paths
only, and never with `back=False`. A frame shows the hub's doors when every root its history can
begin at is a hub destination.
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
    signs_in: bool = False
    """The outcome signs in: its target is a fresh start (Q51)."""

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"from": self.source}
        if self.to:
            out["to"] = self.to
        out["type"] = self.type
        if self.target is not None:
            out["tape" if self.type in ("jump", "call", "hub") else "frame"] = self.target
        if self.resets:
            out["resets_history"] = True
        if self.signs_in:
            out["signs_in"] = True
        out["via"] = self.via
        return out


@dataclass(frozen=True)
class Graph:
    entry: str | None
    nodes: list[str]
    edges: list[Edge]
    starts: tuple[str, ...] = ()
    """Where else a journey can begin: frames opened by their address (Q48)."""

    def out(self, node: str) -> list[Edge]:
        return [e for e in self.edges if e.source == node]


def reachable(g: Graph) -> set[str]:
    """Nodes reachable from the entry, or from an address. `back` only returns to visited nodes, so it
    adds none."""
    seen: set[str] = set()
    if g.entry is None:
        return seen
    queue = deque([g.entry, *g.starts])
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


def closed_cycles(g: Graph, fresh: set[str] = frozenset()) -> list[list[str]]:  # type: ignore[assignment]
    """Cycles the journey can enter but never leave: a terminal component of more than one frame.

    The component that holds the entry is left out: when it is terminal, it is the whole
    reachable app, which is no trap (an app whose frames all reach each other, as with a hub). So,
    as decided in Q51, is one that holds a frame in `fresh`, a sign-in target or a hub destination:
    after a sign-in, that group is the app the user came for, not a trap. Every other closed cycle
    is reported, including one that only a sign-out leads into.
    """
    out = []
    for scc in components(g):
        inside = set(scc)
        if len(scc) < 2 or g.entry in inside or inside & fresh:
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
    """Frames that are a history root on some path, or on every path; back is no way out there (Q31, Q49)."""
    always: set[str] = field(default_factory=set)
    """Roots on every path: nothing enters them with history (Q44). The rest are roots on some paths."""
    fresh: set[str] = field(default_factory=set)
    """Fresh starts (Q51): the entry, hub destinations' first frames, and sign-in targets."""
    beneath: dict[str, str] = field(default_factory=dict)
    """For a frame opened by its address in a hub app, the destination tape put beneath it (Q48): its
    `under=` when that is a destination that reaches it, else the first in hub order that does (Q52)."""
    reaching: dict[str, list[str]] = field(default_factory=dict)
    """For each frame opened by its address, the destination tapes that reach it, in hub order."""
    starts: tuple[str, ...] = ()
    """Frames opened by their address."""
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
        return Graph(self.entry, self.nodes, [*declared, *self.backs, *self.doors], self.starts)


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
    destinations: dict[str, str] = {}
    if app.hub is not None:
        for d in app.hub.destinations:
            t = app.tape(d.tape)
            if t is not None:
                destinations.setdefault(d.tape, t.entry.node)
    keeps = [e for e in edges if e.type in KEEPS_HISTORY and not e.resets]
    static = {n for n in [entry, *destinations.values()] if n} | {e.to for e in edges if e.resets and e.to}

    # Q48: an address opens its frame directly. With a hub, the first destination in hub order whose
    # history reaches the frame goes beneath it; otherwise the address entry is a history root.
    reached = _walk(set(destinations.values()), keeps, static)
    addressed = [n for n in nodes if frames[n].address]
    fresh = {n for n in [entry, *destinations.values()] if n} | {e.to for e in edges if e.signs_in and e.to}
    j = Journey(entry, nodes, edges, fresh=fresh, starts=tuple(addressed))
    for n in addressed:
        if n in static:
            continue
        j.reaching[n] = [t for t, d in destinations.items() if d in reached.get(n, set())]
        chosen = frames[n].under if frames[n].under in j.reaching[n] else next(iter(j.reaching[n]), None)
        if chosen is not None:
            j.beneath[n] = chosen
    j.roots = static | {n for n in addressed if n not in static and n not in j.beneath}

    entered_with_history = {e.to for e in edges if e.to and e.type in ("goto", "jump", "call") and not e.resets}
    j.always = {r for r in j.roots if r not in entered_with_history}
    j.backs = [Edge(n, "back", {"back": "history"}) for n in nodes if n not in j.roots and frames[n].back]
    j.began = _walk(j.roots, keeps, j.roots)
    for n, t in j.beneath.items():
        j.began.setdefault(n, set()).add(destinations[t])
    called = set(_walk({e.to for e in edges if e.type == "call" and e.to}, keeps, j.roots))
    homes = set(destinations.values())
    for n in nodes:
        began = j.began.get(n, set())
        if app.hub is not None and frames[n].hub and n not in called and began and began <= homes:
            j.doors.extend(Edge(n, "hub", {"hub": t}, t, node) for t, node in destinations.items())
    return j
