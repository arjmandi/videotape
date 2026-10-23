"""The intent JSON (05 §6): what `register` will send, and what `videotape check` reads.

The output is deterministic: tapes, frames, components, actions, and edges keep the order they
were written in; records, handlers, and loaders are sorted by name.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ._encode import encode, encode_target, name_of
from .derive import Use, components, frame_records, uses
from .diagnostics import Diagnostic, error
from .intent import Action, App, Frame, Show, Tape
from .outcomes import Outcome
from .records import Record, fields_of, records_in
from .values import VT

FORMAT = "videotape.intent/2"

MOVES = ("goto", "jump", "back", "call", "done")
"""Outcome types that are edges of the journey graph; `stay`, `open`, `download`, `copy` stay put."""


@dataclass(frozen=True)
class Edge:
    """An edge of the journey graph, from a frame, by an action or a handler's declared outcome."""

    source: str
    type: str
    via: dict[str, Any]
    target: str | None = None
    """The tape (jump, call, hub) or frame (goto) the outcome names."""
    to: str | None = None
    """The frame it reaches, when known statically: absent for back and done, and for unknown names."""

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"from": self.source}
        if self.to:
            out["to"] = self.to
        out["type"] = self.type
        if self.target is not None:
            out["tape" if self.type in ("jump", "call", "hub") else "frame"] = self.target
        out["via"] = self.via
        return out


@dataclass
class Built:
    intent: dict[str, Any]
    edges: list[Edge]
    problems: list[Diagnostic] = field(default_factory=list)
    """What building found: two handlers, loaders, or records with one name."""


def resolve(app: App, frame: Frame, kind: str, name: str | None) -> str | None:
    """The node an outcome reaches from `frame`."""
    if kind in ("jump", "call", "hub"):
        t = app.tape(name) if name else None
        return t.entry.node if t else None
    if kind == "goto":
        t = app.tape(frame.tape)
        f = t.frame(name) if t and name else None
        return f.node if f else None
    return None


def outcome_edge(app: App, use: Use, kind: str, name: str | None, via: dict[str, Any]) -> Edge | None:
    if kind not in MOVES:
        return None
    return Edge(use.frame.node, kind, via, name, resolve(app, use.frame, kind, name))


def static_edge(app: App, use: Use) -> Edge | None:
    """The edge a static outcome makes; a handler's edges come from its return type."""
    o = use.target
    if not isinstance(o, Outcome):
        return None
    name = getattr(o, "tape", None) or getattr(o, "frame", None)
    return outcome_edge(app, use, o.type, name, use.via)


def hub_edges(app: App) -> list[Edge]:
    """With a hub, every frame can reach every destination (the hub is everywhere)."""
    if app.hub is None:
        return []
    return [
        Edge(f.node, "hub", {"hub": d.tape}, d.tape, resolve(app, f, "hub", d.tape))
        for f in app.frames
        for d in app.hub.destinations
    ]


class _Names:
    """Handlers and loaders by name; two functions with one name are a problem."""

    def __init__(self, what: str, problems: list[Diagnostic]) -> None:
        self.what, self.problems, self.items = what, problems, {}

    def add(self, fn: Callable[..., Any]) -> str:
        name = name_of(fn)
        known = self.items.setdefault(name, fn)
        if known is not fn and not any(p.at == f"{name}()" for p in self.problems):
            where = f"{getattr(known, '__module__', '?')} and {getattr(fn, '__module__', '?')}"
            self.problems.append(error("duplicate-id", f"two {self.what}s are named {name} ({where})", f"{name}()"))
        return name


class Builder:
    def __init__(self, app: App) -> None:
        self.app = app
        self.problems: list[Diagnostic] = []
        self.handlers = _Names("handler", self.problems)
        self.loaders = _Names("loader", self.problems)
        self.records: list[type[Record]] = []
        self.edges: list[Edge] = []

    def need(self, record: type[Record] | None) -> None:
        if record is None:
            return
        for r in records_in(record):
            if r not in self.records:
                self.records.append(r)

    # ── tapes and frames ──

    def tape(self, t: Tape) -> dict[str, Any]:
        return {"id": t.id, "entry": t.entry.key, "frames": [self.frame(f) for f in t.frames]}

    def frame(self, f: Frame) -> dict[str, Any]:
        out: dict[str, Any] = {"id": f.key}
        if f.id is None:
            out["derived_id"] = True
        out["purpose"] = f.purpose
        if f.title is not None:
            out["title"] = encode(f.title)
        if f.address:
            out["address"] = f.address
        if f.public:
            out["public"] = True
        record = f.shows_record
        if record is not None:
            out["shows"] = {"collection" if f.shows_many else "record": record.__name__}
        if f.edit is not None:
            out["edit"] = {"record": f.edit.__name__}
        if f.enter is not None:
            out["enter"] = {"loader": self.loaders.add(f.enter)}
        if f.submit is not None:
            out["submit"] = {"label": encode(f.submit_label), "handler": self.handlers.add(f.submit_handler)}
        comps, states = components(f)
        out["components"] = comps
        if states:
            out["states"] = states
        if f.actions:
            out["actions"] = [self.action(a) for a in f.actions]
        if f.on_change:
            out["on_change"] = [{"field": str(ref), "handler": self.handlers.add(h)} for ref, h in f.on_change.items()]
        if f.after is not None:
            out["after"] = {"seconds": f.after.seconds, "then": self.target(f.after.then)}

        for r in frame_records(f):
            self.need(r)
            for spec in fields_of(r):
                if "pages" in spec.options:
                    self.loaders.add(spec.options["pages"])
                opts = spec.options.get("options")
                if callable(opts) and not isinstance(opts, type):
                    self.loaders.add(opts)
        for c in f.components:
            if isinstance(c, Show):
                self.need(c.ref.record)
        for u in uses(f):
            if u.handler is not None:
                self.handlers.add(u.handler)
            self.edges.extend(self.use_edges(u))
        return out

    def action(self, a: Action) -> dict[str, Any]:
        out: dict[str, Any] = {"label": encode(a.label), "target": self.target(a.target), "affordance": a.affordance}
        if a.on is not None:
            out["on"] = a.on.__name__
            self.need(a.on)
        if a.to is not None:
            out["to"] = a.to.__name__
            if issubclass(a.to, Record):
                self.need(a.to)
        for key in ("gesture", "key", "role", "importance"):
            if getattr(a, key) is not None:
                out[key] = getattr(a, key)
        for key in ("hidden", "visible"):
            if getattr(a, key) is not None:
                out[key] = encode(getattr(a, key))
        return out

    def target(self, t: Any) -> Any:
        if isinstance(t, Outcome):
            return t.to_json()
        self.handlers.add(t)
        return encode_target(t)

    # ── edges ──

    def use_edges(self, u: Use) -> list[Edge]:
        edge = static_edge(self.app, u)
        return [edge] if edge else []

    # ── records ──

    def record_schemas(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Each record's JSON Schema with `x-vt`, and the built-in types they use (`vt.RichText`, ...)."""
        by_name: dict[str, type[Record]] = {}
        for r in self.records:
            other = by_name.setdefault(r.__name__, r)
            if other is not r:
                self.problems.append(error(
                    "duplicate-id",
                    f"two records are named {r.__name__} ({other.__module__} and {r.__module__})",
                    r.__name__,
                ))  # fmt: skip
        records: dict[str, Any] = {}
        named: dict[str, Any] = {}
        builtins: dict[str, Any] = {}
        for name in sorted(by_name):
            record = by_name[name]
            schema = record.model_json_schema(ref_template="#/records/{model}")
            for def_name, d in schema.pop("$defs", {}).items():
                if _is_builtin(d):
                    d.pop("description", None)
                    builtins[def_name] = d
                elif def_name not in by_name:
                    if named.setdefault(def_name, d) != d:
                        self.problems.append(error("duplicate-id", f"two types are named {def_name}", def_name))
            records[name] = _annotate(record, schema)
        records.update(named)
        moved = {f"#/records/{n}": f"#/types/vt.{n}" for n in builtins}
        return (
            {k: _retarget(records[k], moved) for k in sorted(records)},
            {f"vt.{k}": _retarget(builtins[k], moved) for k in sorted(builtins)},
        )

    # ── the document ──

    def build(self) -> Built:
        app = self.app
        tapes = [self.tape(t) for t in app.tapes]
        self.edges.extend(hub_edges(app))
        out: dict[str, Any] = {"format": FORMAT, "app": app.name, "entry": app.entry}
        if app.world is not None:
            out["world"] = app.world
        if app.hub is not None:
            out["hub"] = [
                {"tape": d.tape, "label": encode(d.label), **({"symbol": d.symbol} if d.symbol else {})}
                for d in app.hub.destinations
            ]
        out["tapes"] = tapes
        out["records"], out["types"] = self.record_schemas()
        out["handlers"] = {name: self.handler(fn) for name, fn in sorted(self.handlers.items.items())}
        out["loaders"] = {name: self.loader(fn) for name, fn in sorted(self.loaders.items.items())}
        out["edges"] = [e.to_json() for e in self.edges if e.type != "hub"]
        return Built(out, self.edges, self.problems)

    def handler(self, fn: Callable[..., Any]) -> dict[str, Any]:
        return {}

    def loader(self, fn: Callable[..., Any]) -> dict[str, Any]:
        return {}


def build(app: App) -> Built:
    return Builder(app).build()


# ── JSON Schema post-processing ──────────────────────────────────────────────

_NONSTANDARD = ("gt", "ge", "lt", "le")  # what Pydantic writes for constraints on custom types such as Money


def _is_builtin(schema: dict[str, Any]) -> bool:
    x = schema.get(VT, {})
    return "part" in x or x.get("type") in ("image", "video", "audio", "richtext", "series")


def _annotate(record: type[Record], schema: dict[str, Any]) -> dict[str, Any]:
    """Each property's `x-vt` gets the field's kind and options; the record is marked as one."""
    props = schema.get("properties", {})
    for spec in fields_of(record):
        prop = props.get(spec.name)
        if prop is None:
            continue
        x = spec.to_json()
        for key in _NONSTANDARD:
            if key in prop:
                x[key] = prop.pop(key)
        prop[VT] = x
    schema[VT] = {"type": "record"}
    return schema


def _retarget(node: Any, moved: dict[str, str]) -> Any:
    """Points references to built-in types at `#/types/vt.Name`."""
    if isinstance(node, list):
        return [_retarget(n, moved) for n in node]
    if isinstance(node, dict):
        return {k: _retarget(v, moved) for k, v in node.items()}
    if isinstance(node, str):
        return moved.get(node, node)
    return node
