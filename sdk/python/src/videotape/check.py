"""`videotape check` (05 §6.3 and §8, 06 §8.2): static checks over an app's intent.

The rules prototype-0's `check.ts` had that still apply are ported (duplicate ids, unknown tapes
and frames, unreachable frames, dead ends, closed cycles, more than one primary action, values
with nowhere to go, events a component cannot report); the rest are v2's, most of them from the
decisions in 05 §18.1. Errors make `videotape check` fail; warnings do not. Running the composer
on the reference screens is not here yet: there is no composer.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Iterator
from typing import Any

from ._encode import name_of
from .decisions import Declared, accepts, read, returns_kind, returns_kinds
from .derive import components, edited_records, field_context, held, input_records, uses
from .diagnostics import Diagnostic, error, warning
from .graph import closed_cycles, has_exit, journey, reachable
from .intent import App, Frame, Show, Tape, Text
from .outcomes import Copy, Outcome
from .records import FieldRef, RecordError, fields_of, kind_of
from .serialize import Built, build, declared_at
from .values import Phrase

RULES: dict[str, tuple[str, str]] = {
    "bad-record": ("error", "a record cannot be read: an undefined type, two vt.Id fields, or an option on the wrong type"),
    "duplicate-id": ("error", "two tapes, frames, addresses, handlers, loaders, or records share a name"),
    "unknown-entry": ("error", "the app's entry tape does not exist"),
    "unknown-tape": ("error", "an outcome, a pick, or the hub names a tape that does not exist"),
    "unknown-frame": ("error", "a goto names a frame its tape does not have"),
    "unnamed-frame": ("error", "a frame in a tape of several has no id="),
    "unreadable-outcome": ("error", "a handler returns an outcome its body does not say, and has no @vt.outcomes"),
    "then-without-result": ("error", "a call's then= handler takes no result parameter"),
    "unknown-document": ("error", "a handler takes a record its frame neither shows nor edits; a loader takes one no earlier frame of its tape has"),
    "ambiguous-record": ("error", "a record is named by its type where the frame holds it more than once"),
    "on-unshown-record": ("error", "an action is on= a record its frame does not show"),
    "secret-shown": ("error", "a frame shows a field of secret type"),
    "hidden-required": ("error", "an edit frame hides a required field other than its vt.Id"),
    "edited-select": ("error", "a list in an edited record has select=; lists the user navigates are shown"),
    "address-param": ("error", "an address has a parameter no loader in its tape takes"),
    "address-standalone": ("error", "a frame opened by its address needs arguments or documents its address does not supply"),
    "bad-under": ("error", "under= on a frame without an address or in an app without a hub, or naming a tape that is not a destination that reaches it"),
    "unsourced-record": ("error", "a shown record has no source: no loader returns it, no earlier frame has it, and it has required fields"),
    "public-without-address": ("error", "a public frame has no address"),
    "loader-returns": ("error", "a loader returns a document its frame neither shows nor edits, or a page its list does not hold"),
    "unknown-field": ("error", "a field reference names a record the frame neither shows nor edits"),
    "not-bool": ("error", "visible= or hidden= names a field that is not a bool"),
    "bad-event": ("error", "vt.show listens for an event its field cannot report"),
    "unknown-argument": ("error", "a jump or call passes an argument no loader or address in the tape it enters takes"),
    "missing-argument": ("error", "a jump, call, or hub destination leaves out an argument a loader in the tape needs"),
    "back-on-root": ("error", "an explicit back on a frame that is a history root on every path"),
    "back-on-root-sometimes": ("warning", "an explicit back on a frame that is a history root on some paths"),
    "multiple-primary": ("warning", "a frame has more than one primary action"),
    "unused-edit": ("warning", "a frame edits a record but nothing receives it"),
    "unreachable-frame": ("warning", "a frame cannot be reached from the entry"),
    "no-exit": ("warning", "a frame has no way out: no declared exit, no back, and no hub (a dead end)"),
    "closed-cycle": ("warning", "frames form a cycle the journey cannot leave"),
    "done-without-call": ("warning", "a tape uses done, but no call enters it"),
}
"""Every rule `check` runs: code → (level, what it finds). Errors make `videotape check` fail."""

_EMPTY = inspect.Parameter.empty


def check(app: App) -> list[Diagnostic]:
    """Every problem `videotape check` finds in `app`, in a fixed order."""
    try:
        built = build(app)
    except RecordError as e:
        return [error("bad-record", str(e))]
    return _Checker(app, built).run()


def _source(via: dict[str, Any]) -> str:
    """Where in a frame an edge comes from, in words: `sign_in()`, `action "Sign in"`, `select Deal.x`."""
    if "handler" in via:
        return f"{via['handler']}()"
    key, value = next(iter(via.items()))
    value = value if isinstance(value, (str, int, float)) else json.dumps(value)
    return f'{key} "{value}"' if key in ("action", "submit") else f"{key} {value}"


def _label(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


def _refs(value: Any) -> Iterator[FieldRef]:
    """Field references inside an outcome's arguments, a copy, a done, or copy's parameters."""
    if isinstance(value, FieldRef):
        yield value
    elif isinstance(value, Phrase):
        yield from _refs(value.params)
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


def _a(word: str) -> str:
    return f"{'an' if word[0] in 'aeiou' else 'a'} {word}"


def _kind_words(kind: Any) -> str:
    if kind.type == "record":
        return kind.target.__name__
    if kind.type in ("collection", "page") and kind.item is not None:
        return f"{'a list' if kind.type == 'collection' else 'a page'} of {_kind_words(kind.item)}"
    return kind.type


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
        self.names()
        self.targets()
        self.returns()
        for f in self.app.frames:
            counts = held(f)
            self.documents(f, counts)
            self.items(f, counts)
            self.secrets(f)
            self.hidden(f)
            self.address(f)
            self.standalone(f)
            self.sourced(f)
            self.loader(f)
            self.fields(f, counts)
            self.primaries(f)
            self.edits(f)
        self.pages()
        self.arguments()
        self.journey()
        self.calls()
        return self.out

    # ── names ──

    def ids(self) -> None:
        for id in _dupes([t.id for t in self.app.tapes]):
            self.report(error("duplicate-id", f"tape '{id}' is defined more than once", id))
        for t in self.app.tapes:
            for id in _dupes([f.id for f in t.frames if f.id]):
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

    def names(self) -> None:
        """A place is its tape plus the frame's id; a tape of several frames names each (Q36)."""
        for t in self.app.tapes:
            if len(t.frames) < 2:
                continue
            for f in t.frames:
                if f.id is None:
                    message = f'"{f.purpose}" is one of {len(t.frames)} frames in tape \'{t.id}\' and needs an id='
                    self.report(error("unnamed-frame", message, f.node))

    def targets(self) -> None:
        for e in self.built.edges:
            if e.type in ("jump", "call") and self.app.tape(e.target) is None:
                if "handler" in e.via:
                    message = f"{e.via['handler']}() returns vt.{e.type}('{e.target}'), but there is no tape '{e.target}'"
                else:
                    message = f"{_source(e.via)} goes to tape '{e.target}', which does not exist"
                self.report(error("unknown-tape", message, e.source))
            elif e.type == "goto" and e.to is None:
                tape_id = e.source.split("/", 1)[0]
                message = f"{_source(e.via)} does goto('{e.target}'), but tape '{tape_id}' has no frame with that id"
                self.report(error("unknown-frame", message, e.source))
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
                self.report(error("unreadable-outcome", problem, f"{name}()"))

    # ── references to records (Q38) ──

    def resolve(self, f: Frame, counts: dict[type, int], record: type, context: tuple[type, ...], where: str,
                missing: str) -> bool:  # fmt: skip
        """Whether `record`, named by its type, means one document here; reports what it cannot."""
        if record in context:
            return True
        n = counts.get(record, 0)
        if n == 0:
            self.report(error(missing, f"{where}: this frame neither shows nor edits {_a(record.__name__)}", f.node))
        elif n > 1:
            message = (f"{where}: this frame holds {record.__name__} {n} times; name the field that holds "
                       f"the one you mean, as in on=Page.toc")  # fmt: skip
            self.report(error("ambiguous-record", message, f.node))
        return n == 1

    def documents(self, f: Frame, counts: dict[type, int]) -> None:
        for u in uses(f):
            if u.handler is None:
                continue
            sig = read(u.handler)
            if sig.problem:
                continue
            if u.continuation and sig.param("result") is None:
                message = f"{sig.name}() is the then= of a call to '{u.via['then']}' but takes no result parameter"
                self.report(error("then-without-result", message, f.node))
            for p in sig.params:
                if u.continuation and p.name == "result":
                    continue
                if u.to is not None and p.annotation is u.to:
                    continue
                if p.annotation is _EMPTY:
                    message = f"{sig.name}() takes {p.name} without a type; annotate it with the record it receives"
                    self.report(error("unknown-document", message, f.node))
                elif p.kind is not None and p.kind.type == "draft":
                    # Q75: a draft is the edited record, unfinished.
                    if f.edit is not p.kind.target:
                        message = (f"{sig.name}() takes {p.name}: vt.Draft[{p.kind.target.__name__}], but this frame "
                                   f"does not edit {p.kind.target.__name__}")  # fmt: skip
                        self.report(error("unknown-document", message, f.node))
                elif p.record is None:
                    shown = getattr(p.annotation, "__name__", repr(p.annotation))
                    message = (f"{sig.name}() takes {p.name}: {shown}, which is neither a record this frame "
                               f"shows or edits nor the target of a move")  # fmt: skip
                    self.report(error("unknown-document", message, f.node))
                else:
                    where = f"{sig.name}() takes {p.name}: {p.record.__name__}"
                    self.resolve(f, counts, p.record, u.context, where, "unknown-document")

    def items(self, f: Frame, counts: dict[type, int]) -> None:
        for a in f.actions:
            if a.on is None:
                continue
            where = f'action "{_label(a.label)}" is on={a.on if isinstance(a.on, FieldRef) else a.on.__name__}'
            if isinstance(a.on, FieldRef):
                if a.on._spec.kind.record is None:
                    self.report(error("on-unshown-record", f"{where}, which holds no records", f.node))
                    continue
                self.resolve(f, counts, a.on._record, (), where, "on-unshown-record")
            else:
                self.resolve(f, counts, a.on, (), where, "on-unshown-record")

    def secrets(self, f: Frame) -> None:
        comps, _ = components(f)
        for node, source in _walk(comps):
            if node.get("type") == "secret" and source == "shows":
                message = f"{node['field']} is a secret, and this frame shows it: secrets are written, never drawn"
                self.report(error("secret-shown", message, f.node))

    def hidden(self, f: Frame) -> None:
        """An edit frame whose form hides a required field can never be complete (Q35); a list it edits
        is edited, not navigated (Q42)."""
        for r in input_records(f):
            for spec in fields_of(r):
                if spec.kind.type == "collection" and "select" in spec.options:
                    message = (f"{spec.ref} is a list the frame edits, so it is not navigated; move it to a "
                               f"record the frame shows, as in shows=[Page, Results]")  # fmt: skip
                    self.report(error("edited-select", message, f.node))
                if spec.required and not spec.shown and not spec.state and spec.kind.type != "id":
                    message = (f"the frame edits {r.__name__}, whose required {spec.name} is not shown, so the "
                               f"form can never be complete; show it, give it a default, or make it a vt.Id")  # fmt: skip
                    self.report(error("hidden-required", message, f.node))

    def address(self, f: Frame) -> None:
        """An address's parameters are the tape's arguments: some loader in the tape takes each (Q46)."""
        if f.public and not f.address:
            self.report(error("public-without-address", "the frame is public but has no address to serve it at", f.node))
        params = f.address_params
        tape = self.app.tape(f.tape)
        if not params or tape is None:
            return
        loaders = [g.enter for g in tape.frames if g.enter is not None]
        for p in params:
            if not any(accepts(loader, p) for loader in loaders):
                takes = "no loader in it takes it" if loaders else "the tape has no loader"
                message = f"address {f.address} passes {p} to tape '{f.tape}', but {takes}"
                self.report(error("address-param", message, f.node))

    def loaded(self, f: Frame) -> list[type] | None:
        """What a frame's loader returns, or None when that cannot be read (then it may return anything)."""
        if f.enter is None:
            return []
        sig = read(f.enter)
        if sig.problem or sig.returns is _EMPTY:
            return None
        return [k.record for k in returns_kinds(sig.returns) if k.record is not None]

    def sourced(self, f: Frame) -> None:
        """Every shown record needs a source when its frame is entered (Q47)."""
        loaded = self.loaded(f)
        if loaded is None:
            return
        earlier = earlier_documents(self.app, f)
        for r, many in f.shown:
            if many or r in loaded or r in earlier:
                continue
            required = [s.name for s in fields_of(r) if s.required]
            if required:
                message = (f"the frame shows {r.__name__}, but nothing gives it one when the frame is entered: "
                           f"no loader returns it, no earlier frame of tape '{f.tape}' has it, and "
                           f"{', '.join(required)} {'has' if len(required) == 1 else 'have'} no default")  # fmt: skip
                self.report(error("unsourced-record", message, f.node))

    def standalone(self, f: Frame) -> None:
        """A frame opened by its address stands on its own: no earlier frame ran (Q48)."""
        if not f.address:
            return
        params = set(f.address_params)
        if f.enter is not None and not read(f.enter).problem:
            sig = read(f.enter)
            for p in sig.params:
                if p.record is not None:
                    message = (f"address {f.address} opens the frame directly, so no earlier frame ran, but "
                               f"{sig.name}() takes {p.name}: {p.record.__name__}")  # fmt: skip
                    self.report(error("address-standalone", message, f.node))
                elif p.required and p.name not in params:
                    message = f"address {f.address} opens the frame directly, but {sig.name}() needs {p.name}, which it does not carry"
                    self.report(error("address-standalone", message, f.node))
        loaded = self.loaded(f)
        if loaded is None:
            return
        earlier = earlier_documents(self.app, f)
        for r, many in f.shown:
            if many or r in loaded or r not in earlier or not any(s.required for s in fields_of(r)):
                continue
            message = (f"address {f.address} opens the frame directly, but it shows {r.__name__}, which only an "
                       f"earlier frame of tape '{f.tape}' has")  # fmt: skip
            self.report(error("address-standalone", message, f.node))

    def loader(self, f: Frame) -> None:
        if f.enter is None:
            return
        sig = read(f.enter)
        if sig.problem:
            self.report(error("loader-returns", f"{sig.name}(): {sig.problem}", f.node))
            return
        earlier = earlier_documents(self.app, f)
        for p in sig.params:
            if p.record is not None and p.record not in earlier:
                message = (f"{sig.name}() takes {p.name}: {p.record.__name__}, which no earlier frame of tape "
                           f"'{f.tape}' shows, edits, or loads")  # fmt: skip
                self.report(error("unknown-document", message, f.node))
        if sig.returns is _EMPTY:
            return
        documents = [kind_of(list[r] if many else r) for r, many in f.shown]
        if f.edit is not None:
            documents.append(kind_of(f.edit))
        wanted = [{**k.to_json(), "nullable": None} for k in documents]
        if f.edit is not None:
            # A saved draft is a starting value for the edited record too (Q72, Q75).
            wanted.append({"type": "draft", "record": f.edit.__name__, "nullable": None})
        for got in returns_kinds(sig.returns):
            if {**got.to_json(), "nullable": None} in wanted:
                continue
            has = ", ".join(_kind_words(k) for k in documents) or "nothing"
            message = f"{sig.name}() returns {_kind_words(got)}, but the frame shows and edits {has}"
            self.report(error("loader-returns", message, f.node))

    def pages(self) -> None:
        """`@vt.pages` loaders: a page of the list's items, from the cursor and the list's holder."""
        for r in self.built.records:
            for spec in fields_of(r):
                loader = spec.pages
                if loader is None:
                    continue
                sig = read(loader)
                at = f"{sig.name}()"
                if spec.kind.type != "collection":
                    self.report(error("loader-returns", f"@vt.pages({spec.ref}): {spec.ref} is not a list", at))
                    continue
                if sig.problem:
                    self.report(error("loader-returns", sig.problem, at))
                    continue
                want = {"type": "page", "item": spec.kind.item.to_json()} if spec.kind.item else None
                if sig.returns is not _EMPTY and returns_kind(sig.returns).to_json() != want:
                    message = (f"@vt.pages({spec.ref}): {sig.name}() returns {_kind_words(returns_kind(sig.returns))}, "
                               f"not a page of {_kind_words(spec.kind.item)}")  # fmt: skip
                    self.report(error("loader-returns", message, at))
                for p in sig.params:
                    if p.name == "cursor" or p.record is spec.record:
                        continue
                    message = (f"@vt.pages({spec.ref}): {sig.name}() takes {p.name}; a pages loader takes the "
                               f"cursor and the {spec.record.__name__} that holds the list")  # fmt: skip
                    self.report(error("unknown-document", message, at))

    def fields(self, f: Frame, counts: dict[type, int]) -> None:
        edited = edited_records(f)
        refs: list[tuple[FieldRef, tuple[type, ...], str]] = []
        flags: list[tuple[FieldRef, str]] = []

        def add_flags(owner: str, options: dict[str, Any], context: tuple[type, ...]) -> None:
            for key in ("visible", "hidden"):
                if isinstance(options.get(key), FieldRef):
                    refs.append((options[key], context, f"{owner} {key}="))
                    flags.append((options[key], f"{owner} {key}="))

        refs.extend((r, (), f"the frame's title {f.title!r}") for r in _refs(f.title))
        for c in f.components:
            if isinstance(c, Text):
                refs.extend((r, (), f"vt.text({getattr(c.value, 'key', c.value)!r})") for r in _refs(c.value))
                continue
            assert isinstance(c, Show)
            if c.on is None:
                refs.append((c.ref, (), f"vt.show({c.ref})"))
            elif self.on_list(f, c):
                refs.append((c.on, (), f"vt.show({c.ref}, on={c.on})"))
                refs.append((c.ref, (c.on._spec.kind.record,), f"vt.show({c.ref}, on={c.on})"))
            refs.extend((r, (c.ref._record,), f"vt.show({c.ref}) press=") for r in _refs(c.options.get("press")))
            add_flags(f"vt.show({c.ref})", c.options.values, (c.ref._record,))
            for event in c.events:
                kind = c.ref._spec.kind.type
                if event == "change" and c.ref._record not in edited:
                    message = f"vt.show({c.ref}, on_change=...): this frame does not edit {c.ref._record.__name__}"
                    self.report(error("bad-event", message, f.node))
                elif event != "change" and kind not in ("video", "audio"):
                    message = (f"vt.show({c.ref}, on_{event}=...): {c.ref} is {_a(kind)} field, and only "
                               f"video and audio report {event}")  # fmt: skip
                    self.report(error("bad-event", message, f.node))
        for ref in f.on_change:
            if ref._record not in edited:
                self.report(error("unknown-field", f"on_change names {ref}, which this frame does not edit", f.node))
            else:
                refs.append((ref, (), f"on_change {ref}"))
        for a in f.actions:
            where = f'action "{_label(a.label)}"'
            context = (a.on_record,) if a.on is not None else ()
            refs.extend((r, context, where) for r in _refs(a.label))
            refs.extend((r, context, where) for r in _refs(a.target))
            add_flags(where, {"visible": a.visible, "hidden": a.hidden}, context)
        if f.submit is not None:
            refs.extend((r, (), "submit=") for r in _refs(f.submit_label))
        for r in counts:
            for spec in fields_of(r):
                context = field_context(spec)
                for key in ("select", "press"):
                    refs.extend((ref, context, f"{spec.ref} {key}=") for ref in _refs(spec.options.get(key)))
                if isinstance(spec.options.get("group_by"), FieldRef):
                    refs.append((spec.options["group_by"], context, f"{spec.ref} group_by="))
                add_flags(str(spec.ref), spec.options, context)
        for ref, context, where in refs:
            self.resolve(f, counts, ref._root, context, f"{where} names {ref}", "unknown-field")
        for ref, where in flags:
            kind = ref._spec.kind.type
            if kind != "boolean":
                self.report(error("not-bool", f"{where} takes a bool field; {ref} is {_a(kind)} field", f.node))

    def on_list(self, f: Frame, c: Show) -> bool:
        """`vt.show(ref, on=list)`: the list holds records, and `ref` is a field of its items (Q41)."""
        assert c.on is not None
        item = c.on._spec.kind.record if c.on._spec.kind.type == "collection" else None
        if item is None:
            message = (f"vt.show({c.ref}, on={c.on}): on= names a list of records; for a single nested record, "
                       f"chain the reference, as in Deal.company.name")  # fmt: skip
            self.report(error("unknown-field", message, f.node))
            return False
        if c.ref._root is not item:
            message = f"vt.show({c.ref}, on={c.on}): {c.ref} is not a field of {c.on}'s items, which are {item.__name__}"
            self.report(error("unknown-field", message, f.node))
            return False
        return True

    def primaries(self, f: Frame) -> None:
        count = (1 if f.submit is not None else 0) + sum(1 for a in f.actions if a.role == "primary")
        if count > 1:
            message = f"{count} primary actions on one frame" + (" (the submit is one)" if f.submit else "")
            self.report(warning("multiple-primary", message, f.node))

    def edits(self, f: Frame) -> None:
        if f.edit is None or f.submit is not None or f.on_change:
            return
        for u in uses(f):
            if u.handler is not None and any(p.record is f.edit or (p.kind is not None and p.kind.type == "draft"
                                                                      and p.kind.target is f.edit) for p in read(u.handler).params):
                return
        message = f"the frame edits {f.edit.__name__}, but no submit, on_change, or action receives it"
        self.report(warning("unused-edit", message, f.node))

    # ── arguments (Q34, Q46) ──

    def arguments(self) -> None:
        """Each jump or call against the tape it enters: the arguments belong to the tape, and any
        frame's loader in it may take them by name."""
        for f in self.app.frames:
            for u in uses(f):
                source = _source(u.via if u.handler is None else {**u.via, "handler": name_of(u.handler)})
                for d in declared_at(u):
                    if d.type in ("jump", "call") and d.target is not None:
                        tape = self.app.tape(d.target)
                        if tape is not None:
                            self.match(tape, f.node, source, d.type, d.args, d.open_args)
        if self.app.hub is not None:
            for dest in self.app.hub.destinations:
                tape = self.app.tape(dest.tape)
                if tape is not None:
                    self.match(tape, "hub", f"the hub's destination '{dest.tape}'", "jump", (), False)

    def match(self, tape: Tape, at: str, source: str, kind: str, args: tuple[str, ...], open_args: bool) -> None:
        taken, required, open_loader = tape_arguments(tape)
        for a in args:
            if a not in taken and not open_loader:
                message = f"{source} does {kind}('{tape.id}', {a}=...), but no loader or address in tape '{tape.id}' takes it"
                self.report(error("unknown-argument", message, at))
        if open_args:
            return
        missing = [name for name in required if name not in args]
        if missing:
            needs = ", ".join(f"{loader}() needs {name}" for name, loader in required.items() if name in missing)
            message = f"{source} does {kind}('{tape.id}') without {', '.join(missing)}: {needs}"
            self.report(error("missing-argument", message, at))

    # ── the journey (Q31, Q32) ──

    def under(self, j: Any) -> None:
        """`under=` names the destination a link opens beneath its frame (Q52)."""
        hub = self.app.hub
        for f in self.app.frames:
            if f.under is None:
                continue
            where = f"under={f.under!r}"
            if not f.address:
                self.report(error("bad-under", f"{where} is for a frame opened by its address, and this one has none", f.node))
            elif hub is None:
                self.report(error("bad-under", f"{where} names a hub destination, but the app has no hub", f.node))
            elif f.under not in [d.tape for d in hub.destinations]:
                message = f"{where} is not a hub destination; the destinations are {', '.join(d.tape for d in hub.destinations)}"
                self.report(error("bad-under", message, f.node))
            elif f.under not in j.reaching.get(f.node, []):
                reach = ", ".join(j.reaching.get(f.node, [])) or "none"
                message = f"{where} cannot reach this frame, so back from it could not return there; the destinations that do: {reach}"
                self.report(error("bad-under", message, f.node))

    def journey(self) -> None:
        if self.app.tape(self.app.entry) is None:
            return
        j = journey(self.app, self.built.edges)
        self.under(j)
        for e in self.built.edges:
            if e.type != "back" or e.source not in j.roots:
                continue
            if e.source in j.always:
                message = f"{_source(e.via)} goes back, but the frame is a history root on every path: there is no history"
                self.report(error("back-on-root", message, e.source))
            else:
                message = (f"{_source(e.via)} goes back, but the frame is a history root on some paths, where the "
                           f"client hides it")  # fmt: skip
                self.report(warning("back-on-root-sometimes", message, e.source))
        g = j.graph
        live = reachable(g)
        frames = {f.node: f for f in self.app.frames}
        for n in g.nodes:
            if n not in live:
                self.report(warning("unreachable-frame", "the frame cannot be reached from the entry", n))
            elif not has_exit(g, n):
                if n in j.always:
                    why = "it is a history root on every path"
                elif n in j.roots:
                    opened = " (its address opens it as one)" if n in j.starts else ""
                    why = f"it is a history root on some paths{opened}"
                else:
                    why = "it has back=False"
                hub = ", and the hub does not show here" if self.app.hub is not None and frames[n].hub else ""
                message = f"the frame has no way out: no declared exit, and no back because {why}{hub}"
                self.report(warning("no-exit", message, n))
        for scc in closed_cycles(g, j.fresh):
            if all(n in live for n in scc):
                self.report(warning("closed-cycle", f"frames {', '.join(scc)} form a cycle with no way out", scc[0]))


    def calls(self) -> None:
        """`done` returns from a call, so a tape that uses it and that no call (or pick) enters has
        nowhere to return to (Q61): its done does nothing."""
        called = {e.target for e in self.built.edges if e.type == "call"}
        warned: set[str] = set()
        for e in self.built.edges:
            tape = e.source.split("/", 1)[0]
            if e.type != "done" or tape in called or tape in warned:
                continue
            warned.add(tape)
            message = f"{_source(e.via)} returns with done, but no call enters tape '{tape}', so there is nothing to return to"
            self.report(warning("done-without-call", message, e.source))


def tape_arguments(tape: Tape) -> tuple[set[str], dict[str, str], bool]:
    """A tape's arguments (Q46): the names its loaders and addresses take, the ones a loader needs
    (with that loader's name), and whether some loader takes any (`**kwargs`). A loader's record
    parameters are documents from earlier frames, not arguments."""
    taken: set[str] = set()
    required: dict[str, str] = {}
    open_loader = False
    for f in tape.frames:
        taken |= set(f.address_params)
        if f.enter is None:
            continue
        try:
            params = inspect.signature(f.enter).parameters.values()
        except (TypeError, ValueError):
            open_loader = True
            continue
        open_loader = open_loader or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params)
        sig = read(f.enter)
        for p in sig.params:
            if p.record is not None:
                continue
            taken.add(p.name)
            if p.required:
                required.setdefault(p.name, sig.name)
    return taken, required, open_loader


def earlier_documents(app: App, frame: Frame) -> list[type]:
    """The documents a frame's loader may take by annotation: those its tape's earlier frames show,
    edit, or load (Q46)."""
    tape = app.tape(frame.tape)
    out: list[type] = []
    for f in tape.frames if tape else []:
        if f is frame:
            break
        out += f.shown_roots + ([f.edit] if f.edit is not None else [])
        if f.enter is not None and not read(f.enter).problem and read(f.enter).returns is not _EMPTY:
            out += [k.record for k in returns_kinds(read(f.enter).returns) if k.record is not None]
    return out
