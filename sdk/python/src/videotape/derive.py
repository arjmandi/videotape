"""What a frame derives from its records (05 §6.1): components, states, and the places where
something happens (an action, a submit, a select, a press, a pick, a timer).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ._encode import encode, encode_target
from .intent import Frame, Show, Text
from .decisions import read
from .outcomes import Call, Outcome, call
from .records import FieldSpec, Record, fields_of, id_field, records_in

AFFORDANCES = ("read", "write", "press", "choose", "adjust", "move", "add", "remove", "scroll", "play")
"""The engine's closed contract (05 §6.4), in canonical order; `pick` from the OS comes after M1."""


@dataclass(frozen=True, eq=False)
class Use:
    """One place in a frame where something happens, and what it does."""

    frame: Frame
    via: dict[str, Any]
    """What in the frame does it, as JSON: `{"action": "Sign in"}`, `{"select": "Dashboard.projects"}`."""
    target: Outcome | Callable[..., Any]
    on: type[Record] | None = None
    """For an action on each item of a collection, the item's record."""
    to: type | None = None
    """For a move, its target."""
    continuation: bool = False
    """The `then=` handler of a call made here: it runs here when the call returns, with `result`."""

    @property
    def handler(self) -> Callable[..., Any] | None:
        return None if isinstance(self.target, Outcome) else self.target


def shown_records(frame: Frame) -> list[type[Record]]:
    """The record the frame shows and every record nested in it."""
    return records_in(frame.shows_record) if frame.shows_record else []


def edited_records(frame: Frame) -> list[type[Record]]:
    """The record the frame edits and every record nested in it."""
    return records_in(frame.edit) if frame.edit else []


def frame_records(frame: Frame) -> list[type[Record]]:
    """Every record on the frame, shown or edited, in first-seen order."""
    out = shown_records(frame)
    return out + [r for r in edited_records(frame) if r not in out]


def uses(frame: Frame) -> list[Use]:
    """Everything that can happen on a frame, in a fixed order."""
    out: list[Use] = []
    if frame.submit is not None:
        out.append(Use(frame, {"submit": encode(frame.submit_label)}, frame.submit_handler))  # type: ignore[arg-type]
    for a in frame.actions:
        via: dict[str, Any] = {"action": encode(a.label)}
        if a.on is not None:
            via["on"] = a.on.__name__
        out.append(Use(frame, via, a.target, a.on, a.to))
    for ref, handler in frame.on_change.items():
        out.append(Use(frame, {"change": str(ref)}, handler))
    for c in frame.components:
        if isinstance(c, Show):
            for event, handler in c.events.items():
                out.append(Use(frame, {event: str(c.ref)}, handler))
            if "press" in c.options.values:
                out.append(Use(frame, {"press": str(c.ref)}, c.options.values["press"]))
    for r in frame_records(frame):
        for f in fields_of(r):
            for key in ("select", "press"):
                if key in f.options:
                    out.append(Use(frame, {key: str(f.ref)}, f.options[key]))
    for r in edited_records(frame):
        for f in fields_of(r):
            if "pick" in f.options:
                out.append(Use(frame, {"pick": str(f.ref)}, call(f.options["pick"])))
    if frame.after is not None:
        out.append(Use(frame, {"after": frame.after.seconds}, frame.after.then))
    # A call's `then=` handler runs here when the call returns, so it is used here too (Q37).
    seen: list[Callable[..., Any]] = []
    for u in out:  # grows while it is read: a continuation may make calls of its own
        if isinstance(u.target, Call):
            calls = [(u.target.tape, u.target.then)]
        elif u.handler is not None:
            calls = [(d.target, d.then) for d in read(u.handler).declared[0] if d.type == "call"]
        else:
            calls = []
        for tape, then in calls:
            if then is not None and then not in seen:
                seen.append(then)
                out.append(Use(frame, {"then": tape}, then, continuation=True))
    return out


# ── components ───────────────────────────────────────────────────────────────


def list_mode(spec: FieldSpec) -> str | None:
    """How a list in an edited record is edited (05 §6.4).

    `"choose"`: a list of an Enum, of options, or of references (records with a `vt.Id`) is a
    multiple choice. `"items"`: any other list takes add, remove, and move. A list with `select=`
    is one to navigate, not to edit, so it has no mode.
    """
    if "select" in spec.options:
        return None
    item = spec.kind.item
    if {"options", "pick"} & set(spec.options) or (item is not None and item.type == "choice"):
        return "choose"
    if item is not None and item.type == "record" and id_field(item.target) is not None:
        return "choose"
    return "items"


def affordances(spec: FieldSpec, editing: bool, moved: set[type]) -> list[str]:
    """What the user can do with a field: read it, write it, choose, adjust, add, scroll, play, ..."""
    kind, opts, got = spec.kind.type, spec.options, set()
    mode = list_mode(spec) if editing and kind == "collection" else None
    if mode == "choose" or (editing and kind != "collection" and "options" in opts):
        got.add("choose")
    elif mode == "items":
        got |= {"move", "add", "remove", "scroll"}
    elif kind in ("video", "audio"):
        got.add("play")
    elif kind == "collection":
        got |= {"read", "scroll"}
        if "select" in opts:
            got.add("press")
        if spec.kind.record in moved:
            got.add("move")
    elif kind == "record":
        if editing and "pick" in opts:
            got.add("press")
    elif editing:
        bounded = {"ge", "gt"} & set(spec.constraints) and {"le", "lt"} & set(spec.constraints)
        if kind in ("choice", "boolean", "date", "datetime", "time"):
            got.add("choose")
        elif kind in ("integer", "number") and bounded:
            got.add("adjust")
        elif kind in ("string", "text", "secret", "money", "integer", "number"):
            got.add("write")
        else:
            got.add("read")
    else:
        got.add("read")
    if "press" in opts:
        got.add("press")
    return [a for a in AFFORDANCES if a in got]


def _derive(
    record: type[Record], editing: bool, moved: set[type], stack: list[type[Record]], source: str | None
) -> tuple[list[dict[str, Any]], list[str]]:
    components: list[dict[str, Any]] = []
    states: list[str] = []
    for f in fields_of(record):
        if f.state:
            states.append(str(f.ref))
            continue
        if not f.shown:
            continue
        node: dict[str, Any] = {"field": str(f.ref)}
        if source:
            node["from"] = source
        node.update(f.to_json())
        node["affordances"] = affordances(f, editing, moved)
        mode = list_mode(f) if editing and f.kind.type == "collection" else None
        if mode == "choose":
            node["many"] = True
        nested = f.kind.record
        if nested is not None and nested not in stack:
            # A picked or chosen record is not edited, nor is a list to choose from or navigate;
            # the items of an edited list are.
            if f.kind.type == "record":
                child_editing = editing and not {"pick", "options"} & set(f.options)
            else:
                child_editing = mode == "items"
            children, child_states = _derive(nested, child_editing, moved, [*stack, nested], None)
            holder = node if f.kind.type == "record" else node["item"]
            holder["components"] = children
            if child_states:
                holder["states"] = child_states
        components.append(node)
    return components, states


def _walk(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for n in nodes:
        out.append(n)
        out.extend(_walk(n.get("components", [])))
        out.extend(_walk(n.get("item", {}).get("components", [])))
    return out


def components(frame: Frame) -> tuple[list[dict[str, Any]], list[str]]:
    """The frame's components and states: what it adds first, then what its records derive.

    `vt.show(...)` overrides every derived component for its field; one the records do not
    derive (a hidden field, or a record the frame does not have) is added.
    """
    moved = {a.on for a in frame.actions if a.to is not None and a.on is not None}
    derived: list[dict[str, Any]] = []
    states: list[str] = []
    shown = frame.shows_record
    if shown is not None:
        comps, st = _derive(shown, False, moved, [shown], None if frame.shows_many else "shows")
        if frame.shows_many:
            item: dict[str, Any] = {"type": "record", "record": shown.__name__, "components": comps}
            if st:
                item["states"] = st
            affs = ["read", "move", "scroll"] if shown in moved else ["read", "scroll"]
            derived.append({"from": "shows", "type": "collection", "item": item, "affordances": affs})
        else:
            derived.extend(comps)
            states.extend(st)
    if frame.edit is not None:
        comps, st = _derive(frame.edit, True, moved, [frame.edit], "edit")
        derived.extend(comps)
        states.extend(st)

    added: list[dict[str, Any]] = []
    shows_scope = shown_records(frame)
    for c in frame.components:
        if isinstance(c, Text):
            added.append({"text": encode(c.value), **c.options.to_json(), "affordances": ["read"]})
            continue
        options = c.options.to_json()
        events = {k: encode_target(v) for k, v in c.events.items()}
        matches = [n for n in _walk(derived) if n.get("field") == str(c.ref)]
        if not matches:
            spec = c.ref.spec
            node: dict[str, Any] = {"field": str(c.ref)}
            if c.ref.record in shows_scope:
                node["from"] = "shows"
            elif c.ref.record in edited_records(frame):
                node["from"] = "edit"
            node.update(spec.to_json())
            node["affordances"] = affordances(spec, node.get("from") == "edit", moved)
            added.append(node)
            matches = [node]
        for node in matches:
            affs = set(node["affordances"])
            node.update(options)
            if events:
                node["events"] = events
            if "press" in options:
                affs.add("press")
            node["affordances"] = [a for a in AFFORDANCES if a in affs]
            node["override"] = True
    return added + derived, states
