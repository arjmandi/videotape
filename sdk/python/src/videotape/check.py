"""`videotape check` (05 §6.3 and §8, 06 §8.2): static checks over an app's intent.

The rules prototype-0's `check.ts` had that still apply are ported (duplicate ids, unknown tapes
and frames, unreachable frames, dead ends, closed cycles, more than one primary action, values
with nowhere to go, events a component cannot report); the rest are v2's. Errors make
`videotape check` fail; warnings do not. Running the composer on the reference screens is not
here yet: there is no composer.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Iterator
from typing import Any

from ._encode import name_of
from .decisions import accepts, read, returns_kind
from .derive import components, edited_records, frame_records, uses
from .diagnostics import Diagnostic, error, warning
from .graph import closed_cycles, graph, has_exit, reachable
from .intent import App, Frame, Show
from .outcomes import Call, Copy, Jump, Outcome
from .records import FieldRef, RecordError, fields_of, kind_of
from .serialize import Built, build

RULES: dict[str, tuple[str, str]] = {
    "unreadable-record": ("error", "a record names a type that is not defined"),
    "duplicate-id": ("error", "two tapes, frames, addresses, handlers, loaders, or records share a name"),
    "unknown-entry": ("error", "the app's entry tape does not exist"),
    "unknown-tape": ("error", "an action, a handler's return type, a pick, or the hub names a tape that does not exist"),
    "unknown-frame": ("error", "a goto names a frame its tape does not have"),
    "goto-unnamed-frame": ("error", "a goto reaches a frame that has no id="),
    "unreadable-return": ("error", "a handler's return type cannot be read, so its edges are unknown"),
    "unknown-document": ("error", "a handler takes a record its frame neither shows nor edits"),
    "on-unshown-record": ("error", "an action is on= a record its frame does not show"),
    "secret-shown": ("error", "a frame shows a field of secret type"),
    "address-param": ("error", "an address has a parameter the frame's loader does not take"),
    "public-without-address": ("error", "a public frame has no address"),
    "loader-returns": ("error", "a frame's loader returns something other than what the frame shows"),
    "unknown-field": ("error", "a field reference names a record the frame neither shows nor edits"),
    "not-bool": ("error", "visible= or hidden= names a field that is not a bool"),
    "bad-event": ("error", "vt.show listens for an event its field cannot report"),
    "unknown-argument": ("error", "a jump or call passes an argument the target's loader does not take"),
    "missing-argument": ("error", "a jump, call, or hub destination leaves out an argument the target's loader needs"),
    "multiple-primary": ("warning", "a frame has more than one primary action"),
    "unused-edit": ("warning", "a frame edits a record but nothing receives it"),
    "unreachable-frame": ("warning", "a frame cannot be reached from the entry"),
    "no-exit": ("warning", "a frame has no way out (a dead end)"),
    "closed-cycle": ("warning", "frames form a cycle the journey cannot leave"),
}
"""Every rule `check` runs: code → (level, what it finds). Errors make `videotape check` fail."""

_EMPTY = inspect.Parameter.empty


def check(app: App) -> list[Diagnostic]:
    """Every problem `videotape check` finds in `app`, in a fixed order."""
    try:
        built = build(app)
    except RecordError as e:
        return [error("unreadable-record", str(e))]
    return _Checker(app, built).run()


def _source(via: dict[str, Any]) -> str:
    """Where in a frame an edge comes from, in words: `sign_in()`, `action "Sign in"`, `select Deal.x`."""
    if "handler" in via:
        return f"{via['handler']}()"
    key, value = next(iter(via.items()))
    value = value if isinstance(value, (str, int, float)) else json.dumps(value)
    return f'{key} "{value}"' if key in ("action", "submit") else f"{key} {value}"


def _refs(value: Any) -> Iterator[FieldRef]:
    """Field references inside an outcome's arguments, a copy, or a done."""
    if isinstance(value, FieldRef):
        yield value
    elif isinstance(value, Copy):
        yield from _refs(value.value)
    elif isinstance(value, Outcome):
        yield from _refs(getattr(value, "args", None))
        yield from _refs(getattr(value, "result", None))
    elif isinstance(value, dict):
        for v in value.values():
            yield from _refs(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _refs(v)


def _walk(nodes: list[dict[str, Any]], source: str | None = None) -> Iterator[tuple[dict[str, Any], str | None]]:
    for n in nodes:
        src = n.get("from", source)
        yield n, src
        yield from _walk(n.get("components", []), src)
        yield from _walk(n.get("item", {}).get("components", []), src)


def _dupes(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for i in items:
        if i in seen and i not in out:
            out.append(i)
        seen.add(i)
    return out


class _Checker:
    def __init__(self, app: App, built: Built) -> None:
        self.app, self.built = app, built
        self.out: list[Diagnostic] = list(built.problems)

    def report(self, d: Diagnostic) -> None:
        if d not in self.out:
            self.out.append(d)

    def run(self) -> list[Diagnostic]:
        self.ids()
        self.entry()
        self.targets()
        self.returns()
        for f in self.app.frames:
            self.documents(f)
            self.items(f)
            self.secrets(f)
            self.address(f)
            self.loader(f)
            self.fields(f)
            self.primaries(f)
            self.edits(f)
        self.arguments()
        self.journey()
        return self.out

    # ── names ──

    def ids(self) -> None:
        for id in _dupes([t.id for t in self.app.tapes]):
            self.report(error("duplicate-id", f"tape '{id}' is defined more than once", id))
        for t in self.app.tapes:
            for id in _dupes([f.key for f in t.frames]):
                self.report(error("duplicate-id", f"frame '{id}' is defined more than once", f"{t.id}/{id}"))
        by_address: dict[str, list[str]] = {}
        for f in self.app.frames:
            if f.address:
                by_address.setdefault(f.address, []).append(f.node)
        for address, nodes in by_address.items():
            if len(nodes) > 1:
                self.report(error("duplicate-id", f"address {address} is used by {', '.join(nodes)}", nodes[1]))

    def entry(self) -> None:
        if self.app.tape(self.app.entry) is None:
            self.report(error("unknown-entry", f"the app's entry tape '{self.app.entry}' does not exist"))

    def targets(self) -> None:
        for e in self.built.edges:
            if e.type in ("jump", "call") and self.app.tape(e.target) is None:
                if "handler" in e.via:
                    said = f"returns vt.{e.type.capitalize()}['{e.target}']"
                    message = f"{e.via['handler']}() {said}, but there is no tape '{e.target}'"
                else:
                    message = f"{_source(e.via)} goes to tape '{e.target}', which does not exist"
                self.report(error("unknown-tape", message, e.source))
            elif e.type == "goto":
                tape_id = e.source.split("/", 1)[0]
                tape = self.app.tape(tape_id)
                target = tape.frame(e.target) if tape and e.target else None
                if target is None:
                    message = f"{_source(e.via)} does goto('{e.target}'), but tape '{tape_id}' has no such frame"
                    self.report(error("unknown-frame", message, e.source))
                elif target.id is None:
                    message = (f"{_source(e.via)} does goto('{e.target}'), which is only the id derived from "
                               f"\"{target.purpose}\"; frames you goto need id='{e.target}'")  # fmt: skip
                    self.report(error("goto-unnamed-frame", message, e.source))
        if self.app.hub is not None:
            for d in self.app.hub.destinations:
                if self.app.tape(d.tape) is None:
                    self.report(error("unknown-tape", f"the hub's destination '{d.tape}' is not a tape", "hub"))

    def handlers(self) -> dict[str, Callable[..., Any]]:
        out: dict[str, Callable[..., Any]] = {}
        for f in self.app.frames:
            for u in uses(f):
                if u.handler is not None:
                    out.setdefault(name_of(u.handler), u.handler)
        return out

    def returns(self) -> None:
        for name, fn in self.handlers().items():
            _, problem = read(fn).declared
            if problem:
                self.report(error("unreadable-return", problem, f"{name}()"))

    # ── per frame ──

    def documents(self, f: Frame) -> None:
        scope = frame_records(f)
        for u in uses(f):
            if u.handler is None:
                continue
            sig = read(u.handler)
            if sig.problem:
                continue
            for p in sig.params:
                if p.annotation is _EMPTY:
                    message = f"{sig.name}() takes {p.name} without a type; annotate it with the record it receives"
                elif p.record is not None and (p.record in scope or p.record is u.to):
                    continue
                elif u.to is not None and p.annotation is u.to:
                    continue
                elif p.record is not None:
                    message = f"{sig.name}() takes {p.name}: {p.record.__name__}, which this frame neither shows nor edits"
                else:
                    shown = getattr(p.annotation, "__name__", repr(p.annotation))
                    message = (f"{sig.name}() takes {p.name}: {shown}, which is neither a record this frame "
                               f"shows or edits nor the target of a move")  # fmt: skip
                self.report(error("unknown-document", message, f.node))

    def items(self, f: Frame) -> None:
        scope = frame_records(f)
        for a in f.actions:
            if a.on is not None and a.on not in scope:
                label = a.label if isinstance(a.label, str) else str(a.label)
                message = f'action "{label}" is on={a.on.__name__}, which this frame does not show'
                self.report(error("on-unshown-record", message, f.node))

    def secrets(self, f: Frame) -> None:
        comps, _ = components(f)
        for node, source in _walk(comps):
            if node.get("type") == "secret" and source == "shows":
                message = f"{node['field']} is a secret, and this frame shows it: secrets are written, never drawn"
                self.report(error("secret-shown", message, f.node))

    def address(self, f: Frame) -> None:
        if f.public and not f.address:
            self.report(error("public-without-address", "the frame is public but has no address to serve it at", f.node))
        params = f.address_params
        if not params:
            return
        if f.enter is None:
            message = f"address {f.address} has {', '.join(params)}, but the frame has no loader to take them"
            self.report(error("address-param", message, f.node))
            return
        for p in params:
            if not accepts(f.enter, p):
                message = f"{name_of(f.enter)}() does not take {p}, which address {f.address} passes"
                self.report(error("address-param", message, f.node))

    def loader(self, f: Frame) -> None:
        if f.enter is None:
            return
        sig = read(f.enter)
        if sig.problem:
            self.report(error("loader-returns", f"{sig.name}(): {sig.problem}", f.node))
            return
        if sig.returns is _EMPTY:
            return
        expected = f.shows if f.shows is not None else f.edit
        got = returns_kind(sig.returns)
        if expected is None:
            message = f"{sig.name}() returns {got.type} {got.record.__name__ if got.record else ''}".rstrip()
            self.report(error("loader-returns", f"{message}, but the frame shows and edits nothing", f.node))
            return
        want = kind_of(expected)
        if {**got.to_json(), "nullable": None} != {**want.to_json(), "nullable": None}:
            message = f"{sig.name}() returns {_kind_words(got)}, but the frame {'shows' if f.shows is not None else 'edits'} {_kind_words(want)}"
            self.report(error("loader-returns", message, f.node))

    def fields(self, f: Frame) -> None:
        scope = frame_records(f)
        edited = edited_records(f)
        refs: list[tuple[FieldRef, str]] = []
        flags: list[tuple[FieldRef, str]] = []

        def add_flags(owner: str, options: dict[str, Any]) -> None:
            for key in ("visible", "hidden"):
                if isinstance(options.get(key), FieldRef):
                    flags.append((options[key], f"{owner} {key}="))

        for c in f.components:
            if isinstance(c, Show):
                refs.append((c.ref, "vt.show"))
                refs.extend((r, f"vt.show({c.ref})") for r in _refs(c.options.get("press")))
                add_flags(f"vt.show({c.ref})", c.options.values)
                for event in c.events:
                    kind = c.ref.spec.kind.type
                    if event == "change" and c.ref.record not in edited:
                        message = f"vt.show({c.ref}, on_change=...): this frame does not edit {c.ref.record.__name__}"
                        self.report(error("bad-event", message, f.node))
                    elif event != "change" and kind not in ("video", "audio"):
                        message = (f"vt.show({c.ref}, on_{event}=...): {c.ref} is {_a(kind)} field, and only "
                                   f"video and audio report {event}")  # fmt: skip
                        self.report(error("bad-event", message, f.node))
        for ref in f.on_change:
            if ref.record not in edited:
                self.report(error("unknown-field", f"on_change names {ref}, which this frame does not edit", f.node))
        for a in f.actions:
            label = a.label if isinstance(a.label, str) else str(a.label)
            where = f'action "{label}"'
            if isinstance(a.label, FieldRef):
                refs.append((a.label, where))
            refs.extend((r, where) for r in _refs(a.target))
            add_flags(where, {"visible": a.visible, "hidden": a.hidden})
        for r in scope:
            for spec in fields_of(r):
                for key in ("select", "press"):
                    refs.extend((ref, f"{spec.ref} {key}=") for ref in _refs(spec.options.get(key)))
                if isinstance(spec.options.get("group_by"), FieldRef):
                    refs.append((spec.options["group_by"], f"{spec.ref} group_by="))
                add_flags(str(spec.ref), spec.options)
        refs.extend(flags)
        for ref, where in refs:
            if ref.record not in scope:
                message = f"{where} names {ref}, but this frame shows and edits no {ref.record.__name__}"
                self.report(error("unknown-field", message, f.node))
        for ref, where in flags:
            kind = ref.spec.kind.type
            if kind != "boolean":
                self.report(error("not-bool", f"{where} takes a bool field; {ref} is {_a(kind)} field", f.node))

    def primaries(self, f: Frame) -> None:
        count = (1 if f.submit is not None else 0) + sum(1 for a in f.actions if a.role == "primary")
        if count > 1:
            message = f"{count} primary actions on one frame" + (" (the submit is one)" if f.submit else "")
            self.report(warning("multiple-primary", message, f.node))

    def edits(self, f: Frame) -> None:
        if f.edit is None or f.submit is not None or f.on_change:
            return
        for u in uses(f):
            if u.handler is not None and any(p.record is f.edit for p in read(u.handler).params):
                return
        message = f"the frame edits {f.edit.__name__}, but no submit, on_change, or action receives it"
        self.report(warning("unused-edit", message, f.node))

    # ── arguments ──

    def arguments(self) -> None:
        for f in self.app.frames:
            for u in uses(f):
                o = u.target
                if isinstance(o, (Jump, Call)):
                    self.pass_args(f.node, _source(u.via), o.type, o.tape, o.args)
        if self.app.hub is not None:
            for d in self.app.hub.destinations:
                self.pass_args("hub", f"the hub's destination '{d.tape}'", "jump", d.tape, {})

    def pass_args(self, at: str, source: str, kind: str, tape_id: str, args: dict[str, Any]) -> None:
        tape = self.app.tape(tape_id)
        if tape is None:
            return
        loader = tape.entry.enter
        if loader is None:
            if args:
                message = f"{source} passes {', '.join(args)} to '{tape_id}', whose first frame has no loader"
                self.report(error("unknown-argument", message, at))
            return
        for a in args:
            if not accepts(loader, a):
                self.report(error("unknown-argument", f"{source} passes {a}, which {name_of(loader)}() does not take", at))
        sig = read(loader)
        if sig.problem:
            return
        missing = [p.name for p in sig.params if p.required and p.name not in args]
        if missing:
            message = f"{source} does {kind}('{tape_id}') without {', '.join(missing)}, which {sig.name}() needs"
            self.report(error("missing-argument", message, at))

    # ── the journey ──

    def journey(self) -> None:
        if self.app.tape(self.app.entry) is None:
            return
        g = graph(self.app, self.built.edges)
        live = reachable(g)
        for n in g.nodes:
            if n not in live:
                self.report(warning("unreachable-frame", "the frame cannot be reached from the entry", n))
            elif not has_exit(g, n):
                self.report(warning("no-exit", "the frame has no way out: a dead end", n))
        for scc in closed_cycles(g):
            if all(n in live for n in scc):
                self.report(warning("closed-cycle", f"frames {', '.join(scc)} form a cycle with no way out", scc[0]))


def _kind_words(kind: Any) -> str:
    if kind.type == "record":
        return kind.target.__name__
    if kind.type in ("collection", "page") and kind.item is not None:
        return f"{'a list' if kind.type == 'collection' else 'a page'} of {_kind_words(kind.item)}"
    return kind.type


def _a(word: str) -> str:
    return f"{'an' if word[0] in 'aeiou' else 'a'} {word}"
