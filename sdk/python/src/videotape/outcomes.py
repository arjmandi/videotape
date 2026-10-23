"""Outcomes: where the journey goes (05 §6.3, 06 §3.4 and §6).

`vt.jump("dashboard")` is an outcome. An action holds one as data; a handler returns one, and the
SDK reads the handler's edges from those returns (`videotape.decisions`).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any, ClassVar

from ._encode import encode, name_of
from .records import FieldRef, Record


class Outcome:
    """Base of every outcome. `to_json` is what the intent and the app protocol carry."""

    type: ClassVar[str]

    def to_json(self) -> dict[str, Any]:
        raise NotImplementedError


@dataclass
class _Identity:
    """`sign_in=user` (the user's record, with its `vt.Id`) or `sign_out=True` on an outcome tells the
    engine who the user is, and starts a fresh history at the target (05 §6.2, §6.3)."""

    sign_in: Any = field(default=None, kw_only=True)
    sign_out: bool = field(default=False, kw_only=True)

    @property
    def resets(self) -> bool:
        return self.sign_in is not None or bool(self.sign_out)

    def _identity(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.sign_in is not None:
            out["sign_in"] = encode(self.sign_in)
        if self.sign_out:
            out["sign_out"] = True
        return out


@dataclass
class Jump(Outcome, _Identity):
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
class Goto(Outcome, _Identity):
    """The next step in the same tape. Frames you goto need an `id=`."""

    type: ClassVar[str] = "goto"
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
class Call(Outcome):
    """A detour to a tape whose `done(result)` reaches `then=`'s handler as its parameter `result`."""

    type: ClassVar[str] = "call"
    tape: str
    args: dict[str, Any] = field(default_factory=dict)
    then: Callable[..., Any] | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": "call", "tape": self.tape}
        if self.then is not None:
            out["then"] = {"handler": name_of(self.then)}
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


def call(tape: str, *, then: Callable[..., Any] | None = None, **args: Any) -> Call:
    """A detour to `tape`, which ends with `vt.done(result)`; `then=` names the handler that receives
    it as its parameter `result`. Without `then=`, the result is dropped."""
    if then is not None and not callable(then):
        raise TypeError("then= takes the handler that receives the call's result")
    return Call(tape, args, then)


def done(result: Any = None) -> Done:
    """End a detour and hand `result` to the caller's `then=` handler."""
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

CONSTRUCTORS: dict[str, Callable[..., Outcome]] = {
    "jump": jump, "goto": goto, "back": back, "stay": stay, "call": call, "done": done, "open": open,
    "download": download,
}  # fmt: skip
"""The outcomes a handler returns, by name; the SDK recognises them in a handler's body by identity."""
