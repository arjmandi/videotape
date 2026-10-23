"""Outcomes: where the journey goes (05 §6.3, 06 §3.4 and §6).

`vt.jump("dashboard")` is an outcome; `vt.Jump["dashboard"]` is its type, which a handler names as
its return type so the journey graph knows the edge without running anything.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Annotated, Any, ClassVar

from ._encode import encode
from .records import FieldRef, Record


class Target:
    """The tape or frame a return type names: the `"dashboard"` in `vt.Jump["dashboard"]`."""

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"Target({self.name!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Target) and other.name == self.name

    def __hash__(self) -> int:
        return hash(self.name)


class Outcome:
    """Base of every outcome. `to_json` is what the intent and the app protocol carry."""

    type: ClassVar[str]

    def to_json(self) -> dict[str, Any]:
        raise NotImplementedError


class _Named(Outcome):
    """An outcome whose type names a target: `vt.Jump["dashboard"]`, `vt.Goto["confirm"]`."""

    def __class_getitem__(cls, name: str) -> Any:
        if not isinstance(name, str):
            raise TypeError(f"vt.{cls.__name__}[...] takes the name of a {cls._names}, such as vt.{cls.__name__}['x']")
        return Annotated[cls, Target(name)]

    _names: ClassVar[str] = "tape"


@dataclass
class _Identity:
    """`sign_in=user_id` or `sign_out=True` on an outcome tells the engine who the user is (05 §6.2)."""

    sign_in: Any = field(default=None, kw_only=True)
    sign_out: bool = field(default=False, kw_only=True)

    def _identity(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.sign_in is not None:
            out["sign_in"] = encode(self.sign_in)
        if self.sign_out:
            out["sign_out"] = True
        return out


@dataclass
class Jump(_Named, _Identity):
    """Switch journey; the current place goes on the history. Arguments reach the tape's loader."""

    type: ClassVar[str] = "jump"
    tape: str
    args: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": "jump", "tape": self.tape}
        if self.args:
            out["args"] = encode(self.args)
        return {**out, **self._identity()}


@dataclass
class Goto(_Named, _Identity):
    """The next step in the same tape. Frames you goto need an `id=`."""

    type: ClassVar[str] = "goto"
    _names: ClassVar[str] = "frame"
    frame: str

    def to_json(self) -> dict[str, Any]:
        return {"type": "goto", "frame": self.frame, **self._identity()}


@dataclass
class Back(Outcome, _Identity):
    """Return to the previous place."""

    type: ClassVar[str] = "back"

    def to_json(self) -> dict[str, Any]:
        return {"type": "back", **self._identity()}


@dataclass
class Stay(Outcome, _Identity):
    """Remain; the document already carries any change."""

    type: ClassVar[str] = "stay"

    def to_json(self) -> dict[str, Any]:
        return {"type": "stay", **self._identity()}


@dataclass
class Call(_Named):
    """A detour to a tape that returns a value to the caller as `ctx.result`."""

    type: ClassVar[str] = "call"
    tape: str
    args: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": "call", "tape": self.tape}
        if self.args:
            out["args"] = encode(self.args)
        return out


@dataclass
class Done(Outcome):
    """The end of a detour, with its result. In an action, `vt.done(Company)` returns the item."""

    type: ClassVar[str] = "done"
    result: Any = None

    def to_json(self) -> dict[str, Any]:
        if isinstance(self.result, type) and issubclass(self.result, Record):
            return {"type": "done", "result": {"item": self.result.__name__}}
        return {"type": "done", "result": encode(self.result)}


@dataclass
class Open(Outcome):
    """Open a link in the system browser or the platform's in-app browser view."""

    type: ClassVar[str] = "open"
    url: Any

    def to_json(self) -> dict[str, Any]:
        return {"type": "open", "url": encode(self.url)}


@dataclass
class Download(Outcome):
    """Hand the user a file: the browser's download on the web."""

    type: ClassVar[str] = "download"
    name: str
    data: str | bytes = ""

    def to_json(self) -> dict[str, Any]:
        if isinstance(self.data, bytes):
            return {"type": "download", "name": self.name, "data": base64.b64encode(self.data).decode(), "encoding": "base64"}
        return {"type": "download", "name": self.name, "data": self.data}


@dataclass
class Copy(Outcome):
    """Copy a field's exact value to the clipboard: `vt.action("Copy", vt.copy(Message.text), on=Message)`."""

    type: ClassVar[str] = "copy"
    value: FieldRef | str

    def to_json(self) -> dict[str, Any]:
        if isinstance(self.value, FieldRef):
            return {"type": "copy", "field": str(self.value)}
        return {"type": "copy", "text": self.value}


def jump(tape: str, *, sign_in: Any = None, sign_out: bool = False, **args: Any) -> Jump:
    """Switch to another tape, with arguments for its loader: `vt.jump("report", project_id=Project.id)`."""
    return Jump(tape, args, sign_in=sign_in, sign_out=sign_out)


def goto(frame: str, *, sign_in: Any = None, sign_out: bool = False) -> Goto:
    """Go to the frame with this `id=` in the same tape."""
    return Goto(frame, sign_in=sign_in, sign_out=sign_out)


def back(*, sign_in: Any = None, sign_out: bool = False) -> Back:
    """Return to the previous place."""
    return Back(sign_in=sign_in, sign_out=sign_out)


def stay(*, sign_in: Any = None, sign_out: bool = False) -> Stay:
    """Remain where the journey is."""
    return Stay(sign_in=sign_in, sign_out=sign_out)


def call(tape: str, **args: Any) -> Call:
    """A detour to `tape`, which ends with `vt.done(result)`."""
    return Call(tape, args)


def done(result: Any = None) -> Done:
    """End a detour and hand `result` to the caller as `ctx.result`."""
    return Done(result)


def open(url: Any) -> Open:  # noqa: A001 - the design's name (05 §6.3)
    """Open a link."""
    return Open(url)


def download(name: str, data: str | bytes) -> Download:
    """Hand the user a file named `name`."""
    return Download(name, data)


def copy(value: FieldRef | str) -> Copy:
    """Copy a field's exact value, never pixels."""
    if not isinstance(value, (FieldRef, str)):
        raise TypeError("vt.copy takes a field reference such as Message.text")
    return Copy(value)


OUTCOME_TYPES: dict[str, type[Outcome]] = {
    c.type: c for c in (Jump, Goto, Back, Stay, Call, Done, Open, Download, Copy)
}
