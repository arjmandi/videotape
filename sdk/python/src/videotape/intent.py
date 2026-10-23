"""Intent: tapes of frames, what they show and edit, and what can be done there (05 §6, 06 §2–§6).

Builders check what they are given as they are called: a wrong type or a malformed id raises at
once. What can only be known from the whole app (unknown tapes, unreachable frames, a handler's
parameters) is for `videotape check`.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, get_args, get_origin

from .outcomes import Outcome
from .records import OPTION_NAMES, FieldOptions, FieldRef, Record
from .values import Phrase

_ID = re.compile(r"[A-Za-z][\w-]{0,63}")
_ADDRESS = re.compile(r"/([\w.~-]+|\{[A-Za-z_]\w*\})?(/([\w.~-]+|\{[A-Za-z_]\w*\}))*")

Target = Outcome | Callable[..., Any]
"""What an action does: a static outcome, or the handler that decides."""


def _check_id(what: str, value: Any) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{what} {value!r}: ids start with a letter and use letters, digits, _ or -")
    return value


def _check_target(what: str, value: Any) -> Target:
    if isinstance(value, Outcome) or (callable(value) and not isinstance(value, type)):
        return value
    raise TypeError(f"{what} takes an outcome such as vt.jump('x'), or a handler; got {value!r}")


def _check_label(what: str, value: Any) -> str | Phrase | FieldRef:
    if isinstance(value, (str, FieldRef)):
        return value
    raise TypeError(f"{what} takes a string, vt.t(...), or a field reference; got {value!r}")


def _check_record(what: str, value: Any) -> type[Record]:
    if isinstance(value, type) and issubclass(value, Record):
        return value
    raise TypeError(f"{what} takes a record class; got {value!r}")


def _check_flag(what: str, value: Any) -> FieldRef | None:
    if value is None or isinstance(value, FieldRef):
        return value
    raise TypeError(f"{what} takes a bool field such as Post.liked, never an expression; got {value!r}")


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug if slug and slug[0].isalpha() else f"frame-{slug}".rstrip("-")


# ── components ───────────────────────────────────────────────────────────────


@dataclass(eq=False)
class Text:
    """A string the records do not carry: `vt.text("Hello, team.", role="heading")`."""

    value: str | Phrase
    options: FieldOptions


def text(
    value: str | Phrase,
    *,
    role: str | None = None,
    importance: str | None = None,
    group: str | None = None,
    order: int | None = None,
    surface: bool | None = None,
) -> Text:
    """A static string on a frame."""
    if not isinstance(value, str):
        raise TypeError(f"vt.text takes a string or vt.t(...); got {value!r}")
    return Text(value, FieldOptions(role=role, importance=importance, group=group, order=order, surface=surface))


SHOW_EVENTS = ("change", "play", "progress", "ended", "error")
"""Events a shown field can report: `change` from an editor; the rest from a media surface (05 §11)."""


@dataclass(eq=False)
class Show:
    """How one field appears, where it differs from the record: `vt.show(Deal.amount, role="heading")`."""

    ref: FieldRef
    options: FieldOptions
    events: dict[str, Callable[..., Any]] = field(default_factory=dict)


def show(
    ref: FieldRef,
    *,
    on_change: Callable[..., Any] | None = None,
    on_play: Callable[..., Any] | None = None,
    on_progress: Callable[..., Any] | None = None,
    on_ended: Callable[..., Any] | None = None,
    on_error: Callable[..., Any] | None = None,
    **options: Any,
) -> Show:
    """Overrides the derived component for `ref`, or adds one; `press=` makes it a control."""
    if not isinstance(ref, FieldRef):
        raise TypeError(f"vt.show takes a field reference such as Deal.amount; got {ref!r}")
    unknown = sorted(set(options) - set(OPTION_NAMES))
    if unknown:
        raise TypeError(f"vt.show got unknown options: {', '.join(unknown)}")
    if "press" in options:
        _check_target("press=", options["press"])
    events = {"change": on_change, "play": on_play, "progress": on_progress, "ended": on_ended, "error": on_error}
    for name, handler in events.items():
        if handler is not None and not callable(handler):
            raise TypeError(f"on_{name}= takes a handler")
    return Show(ref, FieldOptions(**options), {k: v for k, v in events.items() if v is not None})


@dataclass(eq=False)
class Action:
    """A named action: a label, what it does, and what it acts on (06 §6)."""

    label: str | Phrase | FieldRef
    target: Target
    on: type[Record] | None = None
    to: type | None = None
    gesture: str | None = None
    key: str | None = None
    role: str | None = None
    importance: str | None = None
    hidden: FieldRef | None = None
    visible: FieldRef | None = None

    @property
    def affordance(self) -> str:
        return "move" if self.to is not None else "press"


def action(
    label: str | Phrase | FieldRef,
    target: Target,
    *,
    on: type[Record] | None = None,
    to: type | None = None,
    gesture: str | None = None,
    key: str | None = None,
    role: str | None = None,
    importance: str | None = None,
    hidden: FieldRef | None = None,
    visible: FieldRef | None = None,
) -> Action:
    """`on=` makes it an action on each item of a collection; `to=` makes it a move."""
    if on is not None:
        _check_record("on=", on)
    if to is not None and not (isinstance(to, type) and issubclass(to, (Record, Enum))):
        raise TypeError(f"to= takes a record or an Enum, the target of a move; got {to!r}")
    FieldOptions(role=role, importance=importance)  # checks the closed sets
    return Action(
        _check_label("vt.action's label", label), _check_target("vt.action", target), on, to, gesture, key,
        role, importance, _check_flag("hidden=", hidden), _check_flag("visible=", visible),
    )  # fmt: skip


@dataclass(eq=False)
class After:
    """A timer on a frame: `after=vt.after(seconds=5, then=next_story)`."""

    seconds: float
    then: Target


def after(*, seconds: float, then: Target) -> After:
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        raise ValueError("vt.after(seconds=...) takes a positive number")
    return After(seconds, _check_target("vt.after(then=...)", then))


# ── hub ──────────────────────────────────────────────────────────────────────


@dataclass(eq=False)
class Destination:
    """A top-level destination: a tape with its own history."""

    tape: str
    label: str | Phrase
    symbol: str | None = None


def destination(tape: str, label: str | Phrase, *, symbol: str | None = None) -> Destination:
    return Destination(_check_id("destination tape", tape), _check_label("vt.destination's label", label), symbol)


@dataclass(eq=False)
class Hub:
    """Top-level destinations the user moves between freely (06 §3.4)."""

    destinations: list[Destination]


def hub(destinations: Sequence[Destination]) -> Hub:
    items = list(destinations)
    if not items or not all(isinstance(d, Destination) for d in items):
        raise TypeError("vt.hub takes a list of vt.destination(...)")
    return Hub(items)


# ── frames, tapes, the app ───────────────────────────────────────────────────


@dataclass(eq=False)
class Frame:
    """A place: a purpose, what it shows and edits, and what can be done there."""

    purpose: str
    id: str | None = None
    title: str | Phrase | None = None
    shows: Any = None
    edit: type[Record] | None = None
    submit: Callable[..., Any] | Action | None = None
    enter: Callable[..., Any] | None = None
    address: str | None = None
    public: bool = False
    components: list[Text | Show] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    on_change: dict[FieldRef, Callable[..., Any]] = field(default_factory=dict)
    after: After | None = None
    key: str = ""
    """The frame's name in the graph: its `id`, or one derived from its purpose."""
    tape: str = ""

    @property
    def node(self) -> str:
        return f"{self.tape}/{self.key}"

    @property
    def shows_record(self) -> type[Record] | None:
        """The record the frame shows; for `shows=list[Deal]`, `Deal`."""
        if self.shows is None:
            return None
        return get_args(self.shows)[0] if get_origin(self.shows) is list else self.shows

    @property
    def shows_many(self) -> bool:
        return get_origin(self.shows) is list

    @property
    def address_params(self) -> list[str]:
        return re.findall(r"\{(\w+)\}", self.address or "")

    @property
    def submit_handler(self) -> Callable[..., Any] | None:
        return self.submit.target if isinstance(self.submit, Action) else self.submit

    @property
    def submit_label(self) -> str | Phrase | FieldRef:
        return self.submit.label if isinstance(self.submit, Action) else self.purpose


def frame(
    purpose: str,
    *,
    id: str | None = None,  # noqa: A002 - the design's name
    title: str | Phrase | None = None,
    shows: Any = None,
    edit: type[Record] | None = None,
    submit: Callable[..., Any] | Action | None = None,
    enter: Callable[..., Any] | None = None,
    address: str | None = None,
    public: bool = False,
    components: Sequence[Text | Show] = (),
    actions: Sequence[Action] = (),
    on_change: dict[FieldRef, Callable[..., Any]] | None = None,
    after: After | None = None,
) -> Frame:
    """A frame. Its purpose is its accessible title, its primary action's label, and its place's brief."""
    if not isinstance(purpose, str) or not purpose.strip():
        raise TypeError("a frame's first argument is its purpose: one sentence")
    if id is not None:
        _check_id("frame id", id)
    if shows is not None:
        _check_record("shows=", get_args(shows)[0] if get_origin(shows) is list else shows)
    if edit is not None:
        _check_record("edit=", edit)
    if isinstance(submit, Action):
        if submit.on is not None or submit.to is not None:
            raise TypeError("submit= is the frame's own action; it takes no on= or to=")
        if not callable(submit.target) or isinstance(submit.target, Outcome):
            raise TypeError("submit= takes the handler that decides")
    elif submit is not None and not callable(submit):
        raise TypeError("submit= takes a handler, or vt.action(label, handler)")
    if enter is not None and not callable(enter):
        raise TypeError("enter= takes the loader that fetches what the frame shows")
    if address is not None and (not isinstance(address, str) or not _ADDRESS.fullmatch(address)):
        raise ValueError(f"address {address!r}: a path such as '/c/{{id}}', with parameters in braces")
    for c in components:
        if not isinstance(c, (Text, Show)):
            raise TypeError(f"components= takes vt.text(...) and vt.show(...); got {c!r}")
    for a in actions:
        if not isinstance(a, Action):
            raise TypeError(f"actions= takes vt.action(...); got {a!r}")
    changes = dict(on_change or {})
    for ref, handler in changes.items():
        if not isinstance(ref, FieldRef) or not callable(handler):
            raise TypeError("on_change= maps field references to handlers: {Search.q: search_docs}")
    if after is not None and not isinstance(after, After):
        raise TypeError("after= takes vt.after(seconds=..., then=...)")
    return Frame(
        purpose, id, title, shows, edit, submit, enter, address, bool(public), list(components), list(actions),
        changes, after,
    )  # fmt: skip


@dataclass(eq=False)
class Tape:
    """A journey: frames in order; the first is where the tape starts."""

    id: str
    frames: list[Frame]

    @property
    def entry(self) -> Frame:
        return self.frames[0]

    def frame(self, key: str) -> Frame | None:
        return next((f for f in self.frames if f.key == key), None)


def tape(id: str, frames: Sequence[Frame]) -> Tape:  # noqa: A002 - the design's name
    _check_id("tape id", id)
    items = list(frames)
    if not items:
        raise ValueError(f"tape {id!r} has no frames")
    for f in items:
        if not isinstance(f, Frame):
            raise TypeError(f"tape {id!r} takes vt.frame(...); got {f!r}")
        if f.tape and f.tape != id:
            raise ValueError(f"frame {f.purpose!r} is already in tape {f.tape!r}")
    taken = {f.id for f in items if f.id}
    for f in items:
        f.tape = id
        if f.id:
            f.key = f.id
            continue
        base = key = _slug(f.purpose)
        n = 2
        while key in taken:
            key, n = f"{base}-{n}", n + 1
        f.key = key
        taken.add(key)
    return Tape(id, items)


@dataclass(eq=False)
class App:
    """What a developer ships: tapes, an entry, an optional hub, and a world."""

    name: str
    entry: str
    tapes: list[Tape]
    hub: Hub | None = None
    world: str | None = None

    def tape(self, id: str) -> Tape | None:  # noqa: A002
        return next((t for t in self.tapes if t.id == id), None)

    @property
    def frames(self) -> list[Frame]:
        return [f for t in self.tapes for f in t.frames]

    def intent(self) -> dict[str, Any]:
        """The intent JSON (05 §6): records, tapes, frames, components, actions, handlers, and edges."""
        from .serialize import build

        return build(self).intent

    def check(self) -> list[Any]:
        """What `videotape check` finds: a list of `Diagnostic`, errors and warnings."""
        from .check import check

        return check(self)


def app(
    name: str, *, entry: str, tapes: Sequence[Tape], hub: Hub | None = None, world: str | None = None
) -> App:
    _check_id("app name", name)
    items = list(tapes)
    for t in items:
        if not isinstance(t, Tape):
            raise TypeError(f"tapes= takes vt.tape(...); got {t!r}")
    if hub is not None and not isinstance(hub, Hub):
        raise TypeError("hub= takes vt.hub([...])")
    if world is not None and not isinstance(world, str):
        raise TypeError("world= takes the name of a world, such as 'studio'")
    return App(name, entry, items, hub, world)
