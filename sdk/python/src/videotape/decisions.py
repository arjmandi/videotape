"""Decisions: handlers, loaders, and `Reject` (05 §6.3, 06 §5–§6).

Handlers and loaders are plain async functions. A handler's parameters are read with
`typing.get_type_hints` when the app registers (when its intent is built), so postponed
annotations and forward references work: they are the documents it needs, by record type. Its
edges are read from its body (Q33): each `return` of an outcome (`vt.jump("dashboard", ...)`,
under whatever name the module imports videotape as) with a literal tape or frame name, and the
names of its keyword arguments (Q34). Where a return cannot be read, `@vt.outcomes(...)` declares
the edges. `invoke` calls a handler the way the app protocol's `decide` will.
"""

from __future__ import annotations

import ast
import builtins
import inspect
import textwrap
import typing
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, TypeVar

from pydantic import TypeAdapter

from ._encode import encode, name_of
from .outcomes import CONSTRUCTORS, Outcome
from .records import Kind, Record, id_field, kind_of
from .values import Page, Phrase

_EMPTY = inspect.Parameter.empty
_NAMED = {"jump": "tape", "goto": "frame", "call": "tape"}
"""Outcomes that name where they go, and what they name."""


class Reject(Exception):  # noqa: N818 - the design's name
    """Stay on the frame and show `message` as its error status; secrets are cleared (05 §6.3)."""

    def __init__(self, message: str | Phrase) -> None:
        super().__init__(message)
        self.message = message


class UndeclaredOutcome(TypeError):
    """A handler returned an outcome its body and `@vt.outcomes` do not show, so the graph did not know it."""


@dataclass
class Context:
    """What a handler or loader receives first: who the user is (the record `sign_in=` passed)."""

    user: Any = None


# ── declared outcomes ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Declared:
    """An outcome a handler can return, as read from its body: `vt.jump("report", project_id=...)`
    is `("jump", "report", args=("project_id",))`."""

    type: str
    target: str | None = None
    args: tuple[str, ...] = ()
    open_args: bool = False
    """It passes `**kwargs`, so the names of its arguments are not known."""
    resets: bool = False
    """It carries `sign_in` or `sign_out`, so history starts again at its target (Q31)."""
    then: Callable[..., Any] | None = None
    """For a call, the handler that receives its result."""
    implied: bool = False
    line: int | None = field(default=None, compare=False)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.type}
        if self.target is not None:
            out[_NAMED[self.type]] = self.target
        if self.args:
            out["args"] = list(self.args)
        if self.open_args:
            out["args_open"] = True
        if self.resets:
            out["resets_history"] = True
        if self.then is not None:
            out["then"] = {"handler": name_of(self.then)}
        if self.implied:
            out["implied"] = True
        return out

    def allows(self, outcome: Outcome) -> bool:
        if outcome.type != self.type:
            return False
        return self.target is None or self.target == getattr(outcome, _NAMED.get(self.type, ""), None)

    @classmethod
    def of(cls, outcome: Outcome) -> Declared:
        """What a static outcome (in an action, or in `@vt.outcomes`) declares."""
        kind = outcome.type
        return cls(
            kind,
            getattr(outcome, _NAMED[kind]) if kind in _NAMED else None,
            tuple(getattr(outcome, "args", {}) or ()),
            resets=bool(getattr(outcome, "resets", False)),
            then=getattr(outcome, "then", None),
        )


F = TypeVar("F", bound=Callable[..., Any])


def outcomes(*declared: Outcome) -> Callable[[F], F]:
    """Declares a handler's edges where its body cannot say them (a tape named by a variable, an
    outcome a helper builds): `@vt.outcomes(vt.jump("dashboard"), vt.goto("verify"))`.

    Arguments are named with any value (`vt.jump("report", project_id=...)`); for a sign-in, pass
    `sign_in=True`.
    """
    if not declared or not all(isinstance(o, Outcome) and o.type in CONSTRUCTORS for o in declared):
        raise TypeError("@vt.outcomes takes the outcomes the handler returns, such as vt.jump('dashboard')")

    def mark(fn: F) -> F:
        fn.__vt_outcomes__ = declared  # type: ignore[attr-defined]
        return fn

    return mark


# ── reading a handler's body ─────────────────────────────────────────────────


class _Unresolved(Exception):
    pass


class _Names:
    """Looks names up as the handler would: its closure, its module, the builtins."""

    def __init__(self, fn: Callable[..., Any]) -> None:
        self.scopes: list[dict[str, Any]] = []
        try:
            self.scopes.append(dict(inspect.getclosurevars(fn).nonlocals))
        except (TypeError, ValueError):
            pass
        self.scopes += [getattr(fn, "__globals__", {}), vars(builtins)]

    def value(self, node: ast.expr) -> Any:
        if isinstance(node, ast.Name):
            for scope in self.scopes:
                if node.id in scope:
                    return scope[node.id]
            raise _Unresolved(node.id)
        if isinstance(node, ast.Attribute):
            try:
                return getattr(self.value(node.value), node.attr)
            except AttributeError:
                raise _Unresolved(node.attr) from None
        raise _Unresolved(ast.unparse(node))

    def outcome(self, node: ast.expr) -> str | None:
        """The outcome a called name is, by identity: `vt.jump`, `videotape.jump`, or a bare `jump`."""
        try:
            obj = self.value(node)
        except _Unresolved:
            return None
        return next((name for name, fn in CONSTRUCTORS.items() if obj is fn), None)


def _returns(node: ast.AST) -> list[ast.Return]:
    """The function's own `return` statements, in source order; nested functions keep theirs."""
    out: list[ast.Return] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        if isinstance(child, ast.Return):
            out.append(child)
        out.extend(_returns(child))
    return out


def _branches(node: ast.expr) -> list[ast.expr]:
    if isinstance(node, ast.IfExp):
        return _branches(node.body) + _branches(node.orelse)
    return [node]


def _is_off(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value in (None, False)


def _read(expr: ast.expr, names: _Names, line: int) -> Declared | str:
    """One returned expression as a declared outcome, or why it cannot be read."""
    if not isinstance(expr, ast.Call):
        return f"line {line} returns {ast.unparse(expr)}, which is not an outcome such as vt.stay()"
    kind = names.outcome(expr.func)
    if kind is None:
        return f"line {line} returns {ast.unparse(expr.func)}(...), which is not an outcome such as vt.jump(...)"
    target = None
    if kind in _NAMED:
        what = _NAMED[kind]
        node = expr.args[0] if expr.args else next((k.value for k in expr.keywords if k.arg == what), None)
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            shown = ast.unparse(node) if node is not None else "nothing"
            return f"line {line} names the {what} of vt.{kind}(...) with {shown}, not a literal"
        target = node.value
    args: list[str] = []
    open_args = resets = False
    then = None
    for k in expr.keywords:
        if k.arg is None:
            open_args = True
        elif k.arg in ("sign_in", "sign_out"):
            resets = resets or not _is_off(k.value)
        elif k.arg == "then" and kind == "call":
            try:
                then = names.value(k.value)
            except _Unresolved:
                return f"line {line} names the then= handler with {ast.unparse(k.value)}, which cannot be found"
        elif kind in ("jump", "call") and k.arg != _NAMED[kind]:
            args.append(k.arg)
    return Declared(kind, target, tuple(args), open_args, resets, then, line=line)


def read_body(fn: Callable[..., Any]) -> tuple[list[Declared], list[str]]:
    """The outcomes a handler returns, read from its source, and the returns that cannot be read."""
    target = inspect.unwrap(fn)
    try:
        lines, start = inspect.getsourcelines(target)
        tree = ast.parse(textwrap.dedent("".join(lines)))
    except (OSError, TypeError, SyntaxError):
        return [], ["its source cannot be read"]
    node = tree.body[0] if tree.body else None
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return [], ["its source is not a function definition"]
    offset = start - 1
    names = _Names(target)
    found: list[Declared] = []
    unreadable: list[str] = []
    for ret in _returns(node):
        line = offset + ret.lineno
        if ret.value is None or _is_off(ret.value):
            unreadable.append(f"line {line} returns nothing")
            continue
        for expr in _branches(ret.value):
            d = _read(expr, names, line)
            if isinstance(d, str):
                unreadable.append(d)
            elif d not in found:
                found.append(d)
    return found, unreadable


# ── reading a function ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class Param:
    """A parameter after `ctx`: a document by record type, a move's target, a call's `result`, or a
    loader's argument."""

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


@dataclass(eq=False)
class Signature:
    """What Videotape reads from a handler or loader: its parameters, its return annotation (for a
    loader), and its outcomes (for a handler)."""

    fn: Callable[..., Any]
    params: list[Param] = field(default_factory=list)
    returns: Any = _EMPTY
    problem: str | None = None
    """Why its signature or annotations cannot be read, or why it does not take `ctx` first."""

    @property
    def name(self) -> str:
        return name_of(self.fn)

    @cached_property
    def declared(self) -> tuple[list[Declared], str | None]:
        """A handler's outcomes, from its body and `@vt.outcomes`, and why they cannot all be read."""
        if self.problem:
            return [], self.problem
        found, unreadable = read_body(self.fn)
        marked = getattr(self.fn, "__vt_outcomes__", None) or getattr(inspect.unwrap(self.fn), "__vt_outcomes__", None)
        if marked is not None:
            for d in map(Declared.of, marked):
                if d not in found:
                    found.append(d)
            return found, None
        if unreadable:
            return found, "; ".join(unreadable) + "; declare its outcomes with @vt.outcomes(...)"
        if not found:
            return [], "it returns no outcome; return one, such as vt.stay(), or declare them with @vt.outcomes(...)"
        return found, None

    @property
    def outcomes(self) -> list[Declared]:
        """Declared outcomes, and the `Stay` every handler has because it may `Reject`."""
        declared, _ = self.declared
        if any(d.type == "stay" for d in declared):
            return declared
        return [*declared, Declared("stay", implied=True)]

    def param(self, name: str) -> Param | None:
        return next((p for p in self.params if p.name == name), None)

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


def returns_kind(annotation: Any) -> Kind:
    """What a loader returns: a record, a list, or a page of a list (`vt.Page[Post]`)."""
    if isinstance(annotation, type) and issubclass(annotation, Page):
        args = annotation.__pydantic_generic_metadata__.get("args") or (Any,)
        return Kind("page", item=kind_of(args[0]))
    return kind_of(annotation)


_cache: dict[Callable[..., Any], Signature] = {}


def read(fn: Callable[..., Any]) -> Signature:
    """Reads a handler's or loader's signature, once. Problems are recorded, never raised."""
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


def _check_identity(name: str, outcome: Outcome) -> None:
    user = getattr(outcome, "sign_in", None)
    if user is None:
        return
    if not (isinstance(user, Record) and (key := id_field(type(user))) and getattr(user, key) is not None):
        raise TypeError(f"{name}() signs in with {user!r}; sign_in= takes the user's record, with its vt.Id set")


async def invoke(handler: Callable[..., Any], ctx: Any, /, **documents: Any) -> dict[str, Any]:
    """Calls a handler as `decide` will, and returns the outcome record the engine would get.

    Documents are passed by parameter name, as records or as their JSON, and validated against
    the parameter's type; so is a call's `result`. A `Reject` becomes `{"type": "reject",
    "message": ...}`. An outcome the body and `@vt.outcomes` do not show raises
    `UndeclaredOutcome`, because the graph did not know it.
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
        said = ", ".join(f"{d.type}({d.target})" if d.target else f"{d.type}()" for d in declared)
        raise UndeclaredOutcome(f"{sig.name}() returned {result.to_json()}, but its body shows only {said}")
    _check_identity(sig.name, result)
    return result.to_json()
