"""Decisions: handlers, loaders, and `Reject` (05 §6.3, 06 §5–§6).

Handlers and loaders are plain async functions. Their annotations are read with
`typing.get_type_hints` when the app registers (when its intent is built), so postponed
annotations and forward references work: a handler's parameters are the documents it needs, by
record type; its return type is its edges. `invoke` calls one the way the app protocol's `decide`
will, and turns its return or its `Reject` into an outcome record.
"""

from __future__ import annotations

import inspect
import types
import typing
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cached_property
from typing import Annotated, Any, Union, get_args, get_origin

from pydantic import TypeAdapter

from ._encode import encode, name_of
from .outcomes import Call, Goto, Jump, Outcome, Target
from .records import Kind, Record, kind_of
from .values import Page, Phrase

_EMPTY = inspect.Parameter.empty


class Reject(Exception):  # noqa: N818 - the design's name
    """Stay on the frame and show `message` as its error status; secrets are cleared (05 §6.3)."""

    def __init__(self, message: str | Phrase) -> None:
        super().__init__(message)
        self.message = message


class UndeclaredOutcome(TypeError):
    """A handler returned an outcome its return type does not declare, so the graph did not know it."""


@dataclass
class Context:
    """What a handler or loader receives first: who the user is, and what a call returned."""

    user: Any = None
    result: Any = None


# ── reading a function ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class Param:
    """A parameter after `ctx`: a document by record type, a move's target, or a loader's argument."""

    name: str
    annotation: Any
    required: bool
    default: Any = None

    @property
    def kind(self) -> Kind | None:
        return None if self.annotation is _EMPTY else kind_of(self.annotation)

    @property
    def record(self) -> type[Record] | None:
        """The record this parameter receives, when it receives one (not a list of them)."""
        kind = self.kind
        return kind.target if kind is not None and kind.type == "record" else None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name}
        if self.kind is not None:
            out.update(self.kind.to_json())
        out["required"] = self.required
        if not self.required:
            try:
                out["default"] = encode(self.default)
            except TypeError:
                pass
        return out


@dataclass(frozen=True)
class Declared:
    """An outcome a handler's return type declares: `vt.Jump["dashboard"]` is `("jump", "dashboard")`."""

    type: str
    target: str | None = None
    implied: bool = False

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.type}
        if self.target is not None:
            out["frame" if self.type == "goto" else "tape"] = self.target
        if self.implied:
            out["implied"] = True
        return out

    def allows(self, outcome: Outcome) -> bool:
        if outcome.type != self.type:
            return False
        return self.target is None or self.target == getattr(outcome, "tape", getattr(outcome, "frame", None))


_NAMED = {Jump: "tape", Goto: "frame", Call: "tape"}


def _members(annotation: Any) -> list[Any]:
    if get_origin(annotation) in (Union, types.UnionType):
        return [m for a in get_args(annotation) for m in _members(a)]
    return [annotation]


@dataclass(eq=False)
class Signature:
    """What Videotape reads from a handler or loader: its parameters and its return type."""

    fn: Callable[..., Any]
    params: list[Param] = field(default_factory=list)
    returns: Any = _EMPTY
    problem: str | None = None
    """Why its annotations cannot be read, or why it does not take `ctx` first."""

    @property
    def name(self) -> str:
        return name_of(self.fn)

    @cached_property
    def declared(self) -> tuple[list[Declared], str | None]:
        """A handler's outcomes from its return type, and why they cannot be read, if they cannot."""
        if self.problem:
            return [], self.problem
        if self.returns is _EMPTY:
            return [], "it has no return type; write one, such as -> vt.Jump['dashboard'] | vt.Stay"
        out: list[Declared] = []
        for m in _members(self.returns):
            base, meta = (get_args(m)[0], get_args(m)[1:]) if get_origin(m) is Annotated else (m, ())
            if not (isinstance(base, type) and issubclass(base, Outcome)):
                return [], f"its return type names {_show(m)}, which is not an outcome such as vt.Stay"
            target = next((t.name for t in meta if isinstance(t, Target)), None)
            if base in _NAMED and target is None:
                what = _NAMED[base]
                return [], f"its return type says vt.{base.__name__} without the {what}: write vt.{base.__name__}['name']"
            d = Declared(base.type, target)
            if d not in out:
                out.append(d)
        return out, None

    @property
    def outcomes(self) -> list[Declared]:
        """Declared outcomes, and the `Stay` every handler has because it may `Reject`."""
        declared, _ = self.declared
        if any(d.type == "stay" for d in declared):
            return declared
        return [*declared, Declared("stay", implied=True)]

    def allows(self, outcome: Outcome) -> bool:
        return outcome.type == "stay" or any(d.allows(outcome) for d in self.declared[0])

    def handler_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"params": [p.to_json() for p in self.params]}
        out["outcomes"] = [d.to_json() for d in self.outcomes]
        _, problem = self.declared
        if problem:
            out["unreadable"] = problem
        return out

    def loader_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"params": [p.to_json() for p in self.params]}
        if self.problem:
            out["unreadable"] = self.problem
        elif self.returns is not _EMPTY:
            out["returns"] = returns_kind(self.returns).to_json()
        return out


def _show(annotation: Any) -> str:
    return getattr(annotation, "__name__", None) or repr(annotation)


def returns_kind(annotation: Any) -> Kind:
    """What a loader returns: a record, a list, or a page of a list (`vt.Page[Post]`)."""
    if isinstance(annotation, type) and issubclass(annotation, Page):
        args = annotation.__pydantic_generic_metadata__.get("args") or (Any,)
        return Kind("page", item=kind_of(args[0]))
    return kind_of(annotation)


_cache: dict[Callable[..., Any], Signature] = {}


def read(fn: Callable[..., Any]) -> Signature:
    """Reads a handler's or loader's annotations, once. Problems are recorded, never raised."""
    if fn in _cache:
        return _cache[fn]
    sig = Signature(fn)
    try:
        params = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError) as e:
        sig.problem = f"its signature cannot be read: {e}"
        params = []
    try:
        hints = typing.get_type_hints(fn, include_extras=True)
    except Exception as e:  # noqa: BLE001 - any failure to evaluate an annotation is reported
        sig.problem = sig.problem or f"its annotations cannot be read: {type(e).__name__}: {e}"
        hints = {}
    positional = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    if not sig.problem and (not params or params[0].kind not in positional):
        sig.problem = "it does not take ctx as its first parameter"
    for p in params[1:]:
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        annotation = hints.get(p.name, p.annotation)
        sig.params.append(Param(p.name, annotation, p.default is _EMPTY, None if p.default is _EMPTY else p.default))
    sig.returns = hints.get("return", _EMPTY)
    _cache[fn] = sig
    return sig


def accepts(fn: Callable[..., Any], name: str) -> bool:
    """Whether a loader takes an argument by this name (or any, with `**kwargs`)."""
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return True
    return any(p.name == name or p.kind is inspect.Parameter.VAR_KEYWORD for p in params)


# ── calling a handler ────────────────────────────────────────────────────────


def _coerce(param: Param, value: Any) -> Any:
    """A document as its record (from its JSON, if need be); a move's target as its type."""
    if param.annotation is _EMPTY:
        return value
    if isinstance(param.annotation, type) and isinstance(value, param.annotation):
        return value
    return TypeAdapter(param.annotation).validate_python(value)


async def invoke(handler: Callable[..., Any], ctx: Any, /, **documents: Any) -> dict[str, Any]:
    """Calls a handler as `decide` will, and returns the outcome record the engine would get.

    Documents are passed by parameter name, as records or as their JSON, and validated against
    the parameter's type. A `Reject` becomes `{"type": "reject", "message": ...}`. An outcome the
    return type does not declare raises `UndeclaredOutcome`, because the graph did not know it.
    """
    sig = read(handler)
    declared, problem = sig.declared
    if problem:
        raise TypeError(f"{sig.name}() cannot be called as a decision: {problem}")
    names = {p.name for p in sig.params}
    unknown = sorted(set(documents) - names)
    if unknown:
        raise TypeError(f"{sig.name}() has no parameter {', '.join(unknown)}")
    kwargs = {}
    for p in sig.params:
        if p.name in documents:
            kwargs[p.name] = _coerce(p, documents[p.name])
        elif p.required:
            raise TypeError(f"{sig.name}() needs {p.name}")
    try:
        result = handler(ctx, **kwargs)
        if inspect.isawaitable(result):
            result = await result
    except Reject as r:
        return {"type": "reject", "message": encode(r.message)}
    if not isinstance(result, Outcome):
        raise UndeclaredOutcome(f"{sig.name}() returned {result!r}, which is not an outcome")
    if not sig.allows(result):
        said = " | ".join(f"{d.type}[{d.target}]" if d.target else d.type for d in declared)
        raise UndeclaredOutcome(f"{sig.name}() returned {result.to_json()}, but its return type says {said}")
    return result.to_json()
