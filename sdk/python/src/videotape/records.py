"""Records: typed data models the engine derives components from (05 §6.1, 06 §4).

A record is a Pydantic model. Field options say what the type cannot (`role`, `group`, `select`,
...) and travel in the JSON Schema under `x-vt`. On the class, a field name is a reference
(`Deal.amount`), which is how frames, actions, and arguments point at fields without paths.
"""

from __future__ import annotations

import ast
import copy
import sys
import types
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, ClassVar, Literal, Union, get_args, get_origin

import pydantic
from pydantic import BaseModel, ConfigDict, field_validator
from pydantic._internal._model_construction import ModelMetaclass
from pydantic.errors import PydanticUndefinedAnnotation
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from ._encode import encode, encode_target, name_of
from .values import BUILTIN_TYPES, VT, Id, Phrase, Text

ROLES = ("heading", "primary", "secondary", "navigation", "status", "supporting")
IMPORTANCE = ("required", "normal", "optional")
OPTION_NAMES = (
    "role", "importance", "group", "order", "format", "lines", "kind", "commit", "options", "select",
    "anchor", "min_items", "max_items", "group_by", "surface", "show", "visible", "hidden", "press", "label",
)  # fmt: skip
_CLOSED = {
    "role": ROLES,
    "importance": IMPORTANCE,
    "anchor": ("start", "end"),
    "commit": ("submit", "blur", "change"),
}


class RecordError(TypeError):
    """A record that cannot be read: an undefined name in an annotation, two ids, or an option on a
    field of the wrong type."""


# ── field references ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FieldRef:
    """A field of a record, written `Deal.amount`. In an action's arguments it means this item's value.

    A reference reaches into a single nested record by chaining, `Deal.company.name` (Q41); a list's
    items are reached with `on=` instead, as in `vt.show(Entry.title, on=Page.toc)`. The reference's
    own attributes start with `_`, which no record field can, so any field name can follow it.
    """

    _record: type[Record]
    _name: str
    _via: FieldRef | None = None
    """For a chained reference, the field that holds this field's record: `Deal.company`."""

    def __str__(self) -> str:
        return f"{self._via}.{self._name}" if self._via is not None else f"{self._record.__name__}.{self._name}"

    def __repr__(self) -> str:
        return str(self)

    def __getattr__(self, attr: str) -> FieldRef:
        if attr.startswith("_"):
            raise AttributeError(attr)
        kind = self._spec.kind
        if kind.type == "record" and attr in kind.target.model_fields:
            return FieldRef(kind.target, attr, self)
        if kind.type == "collection" and kind.record is not None and attr in kind.record.model_fields:
            raise AttributeError(
                f"{self} is a list; reach its items' fields with on=, as in "
                f"vt.show({kind.record.__name__}.{attr}, on={self})"
            )
        raise AttributeError(f"{self} has no field {attr!r}")

    def to_json(self) -> dict[str, str]:
        return {"field": str(self)}

    @property
    def _spec(self) -> FieldSpec:
        return next(f for f in fields_of(self._record) if f.name == self._name)

    @property
    def _root(self) -> type[Record]:
        """The record a chained reference starts at: `Deal` for `Deal.company.name`."""
        return self._via._root if self._via is not None else self._record

    @property
    def _path(self) -> list[FieldRef]:
        """The references from the root to this one: `[Deal.company, Deal.company.name]`."""
        return [*(self._via._path if self._via is not None else []), self]


# ── field options ────────────────────────────────────────────────────────────


class FieldOptions:
    """Videotape's options on one field. Pydantic calls it to write them into JSON Schema as `x-vt`."""

    __slots__ = ("values",)

    def __init__(self, **values: Any) -> None:
        self.values = {k: v for k, v in values.items() if v is not None}
        for key, allowed in _CLOSED.items():
            if key in self.values and self.values[key] not in allowed:
                raise ValueError(f"{key}={self.values[key]!r}: expected one of {', '.join(allowed)}")
        for key in ("surface", "show", "state"):
            if key in self.values and not isinstance(self.values[key], bool):
                raise TypeError(f"{key}= takes True or False")
        if "order" in self.values and not isinstance(self.values["order"], int):
            raise TypeError("order= takes an int")
        for key in ("visible", "hidden", "group_by"):
            if key in self.values and not isinstance(self.values[key], FieldRef):
                raise TypeError(f"{key}= takes a field reference such as Post.liked, never an expression")
        if "lines" in self.values:
            lines = self.values["lines"]
            low, high = (lines, lines) if isinstance(lines, int) else tuple(lines)
            if not (isinstance(low, int) and isinstance(high, int) and 1 <= low <= high):
                raise ValueError(f"lines={lines!r}: a number of lines, or (fewest, most), with 1 <= fewest <= most")
            self.values["lines"] = (low, high)
        for key in ("min_items", "max_items"):
            if key in self.values and (not isinstance(self.values[key], int) or self.values[key] < 0):
                raise TypeError(f"{key}= takes a count")

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def __call__(self, schema: dict[str, Any]) -> None:
        schema.setdefault(VT, {}).update(self.to_json())

    def __repr__(self) -> str:
        return "FieldOptions(" + ", ".join(f"{k}={v!r}" for k, v in self.values.items()) + ")"

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in self.values.items():
            if key == "options" and callable(value) and not isinstance(value, type):
                out[key] = {"loader": name_of(value)}
            elif key in ("select", "press"):
                out[key] = encode_target(value)
            else:
                out[key] = encode(value)
        return out


def _field(default: Any, options: FieldOptions, constraints: dict[str, Any]) -> Any:
    if "json_schema_extra" in constraints:
        raise TypeError("vt.Field writes Videotape's options into json_schema_extra; pass neither")
    return pydantic.Field(default, json_schema_extra=options, **constraints)


def Field(
    default: Any = PydanticUndefined,
    *,
    role: str | None = None,
    importance: str | None = None,
    group: str | None = None,
    order: int | None = None,
    format: str | None = None,
    kind: str | None = None,
    commit: str | None = None,
    options: Any = None,
    select: Any = None,
    anchor: str | None = None,
    lines: int | tuple[int, int] | None = None,
    min_items: int | None = None,
    max_items: int | None = None,
    group_by: Any = None,
    surface: bool | None = None,
    show: bool | None = None,
    visible: Any = None,
    hidden: Any = None,
    press: Any = None,
    label: str | None = None,
    **constraints: Any,
) -> Any:
    """A record field with Videotape's options (06 §4) and Pydantic's (`ge=`, `max_length=`, ...).

    `min_items=` and `max_items=` bound an edited list and are enforced as Pydantic's `min_length`
    and `max_length`. A paged list registers its loader with `@vt.pages(Record.field)`.
    """
    if "pages" in constraints:
        raise TypeError("pages= is gone: register the loader after the record with @vt.pages(Record.field)")
    opts = FieldOptions(
        role=role, importance=importance, group=group, order=order, format=format, lines=lines, kind=kind,
        commit=commit, options=options, select=select, anchor=anchor, min_items=min_items,
        max_items=max_items, group_by=group_by, surface=surface, show=show, visible=visible, hidden=hidden,
        press=press, label=label,
    )  # fmt: skip
    if min_items is not None:
        constraints.setdefault("min_length", min_items)
    if max_items is not None:
        constraints.setdefault("max_length", max_items)
    return _field(default, opts, constraints)


def State(default: Any = False, **constraints: Any) -> Any:
    """An item state the world may show (`pending`, `unread`, `mine`), never drawn as text."""
    return _field(default, FieldOptions(state=True), constraints)


def pick(tape: str, *, default: Any = PydanticUndefined, **kwargs: Any) -> Any:
    """A field filled by a call to `tape`, which returns the record with `done(...)` (06 §4)."""
    options = {k: kwargs.pop(k) for k in OPTION_NAMES if k in kwargs}
    return _field(default, FieldOptions(pick=tape, **options), kwargs)


# ── what a type is ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Kind:
    """What a field's type is to Videotape: `string`, `text`, `choice`, `record`, `collection`, ..."""

    type: str
    target: Any = None
    item: Kind | None = None
    lines: tuple[int, int] | None = None
    choices: tuple[Any, ...] | None = None
    nullable: bool = False

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.type}
        if self.type == "record":
            out["record"] = self.target.__name__
        elif self.type == "choice":
            if self.target is not None:
                out["enum"] = self.target.__name__
            else:
                out["choices"] = [encode(c) for c in self.choices or ()]
        if self.lines:
            out["lines"] = list(self.lines)
        if self.item:
            out["item"] = self.item.to_json()
        if self.nullable:
            out["nullable"] = True
        return out

    @property
    def record(self) -> type[Record] | None:
        """The record this kind holds: itself, or a collection's item."""
        if self.type == "record":
            return self.target
        if self.item is not None:
            return self.item.record
        return None


_UNION_ORIGINS = (Union, types.UnionType)
_SEQUENCES = (list, tuple, set, frozenset)


def kind_of(annotation: Any, metadata: list[Any] | tuple[Any, ...] = ()) -> Kind:
    """Reads a field's annotation (and Pydantic's metadata for it) as a `Kind`."""
    meta = list(metadata)
    t = annotation
    nullable = False
    while True:
        origin = get_origin(t)
        if origin is Annotated:
            t, *extra = get_args(t)
            meta.extend(extra)
        elif origin in _UNION_ORIGINS:
            args = [a for a in get_args(t) if a is not type(None)]
            nullable = nullable or len(args) < len(get_args(t))
            if len(args) != 1:
                return Kind("data", nullable=nullable)
            t = args[0]
        else:
            break
    origin = get_origin(t)
    if origin in _SEQUENCES or t in _SEQUENCES:
        args = [a for a in get_args(t) if a is not Ellipsis]
        item = kind_of(args[0]) if args else Kind("data")
        return Kind("collection", item=item, nullable=nullable)
    if origin is Literal:
        return Kind("choice", choices=get_args(t), nullable=nullable)
    if isinstance(t, type):
        if t is Text:
            return Kind("text", target=t, lines=Text.LINES, nullable=nullable)
        if t in BUILTIN_TYPES:
            return Kind(BUILTIN_TYPES[t], target=t, nullable=nullable)
        if issubclass(t, Record):
            return Kind("record", target=t, nullable=nullable)
        if issubclass(t, Enum):
            return Kind("choice", target=t, nullable=nullable)
        for py, name in _SCALARS:
            if issubclass(t, py):
                return Kind(name, nullable=nullable)
    return Kind("data", nullable=nullable)


_SCALARS: tuple[tuple[type, str], ...] = (
    (bool, "boolean"),
    (int, "integer"),
    (float, "number"),
    (Decimal, "number"),
    (datetime, "datetime"),
    (date, "date"),
    (time, "time"),
    (str, "string"),
)


# ── fields ───────────────────────────────────────────────────────────────────

_CONSTRAINTS = ("gt", "ge", "lt", "le", "multiple_of", "min_length", "max_length", "pattern")


@dataclass(frozen=True)
class FieldSpec:
    """One field of a record, as Videotape reads it."""

    record: type[Record]
    name: str
    kind: Kind
    required: bool
    options: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)

    @property
    def ref(self) -> FieldRef:
        return FieldRef(self.record, self.name)

    @property
    def state(self) -> bool:
        return bool(self.options.get("state"))

    @property
    def shown(self) -> bool:
        """Whether the field becomes a component: not `show=False`, not a state, and not an `Id`."""
        return self.options.get("show", True) and not self.state and self.kind.type != "id"

    @property
    def pages(self) -> Any:
        """The loader `@vt.pages` registered for this field, if any."""
        return self.record.__dict__.get("__vt_pages__", {}).get(self.name)

    def to_json(self) -> dict[str, Any]:
        """The field's `x-vt`: its kind, then its options."""
        out = self.kind.to_json()
        opts = FieldOptions(**self.options).to_json() if self.options else {}
        if self.pages is not None:
            opts["pages"] = {"loader": name_of(self.pages)}
        return {**out, **opts}


_fields_cache: dict[type, list[FieldSpec]] = {}


def ensure_complete(cls: type[Record]) -> None:
    """Resolves a record's forward references, or says which name is missing."""
    if cls.__pydantic_complete__:
        return
    try:
        cls.model_rebuild(raise_errors=True)
    except PydanticUndefinedAnnotation as e:
        raise RecordError(f"record {cls.__name__} names {e.name}, which is not defined") from None


def fields_of(cls: type[Record]) -> list[FieldSpec]:
    """A record's fields in declaration order."""
    if cls in _fields_cache:
        return _fields_cache[cls]
    ensure_complete(cls)
    out = []
    for name, info in cls.model_fields.items():
        options = info.json_schema_extra.values if isinstance(info.json_schema_extra, FieldOptions) else {}
        constraints = {}
        for m in info.metadata:
            for key in _CONSTRAINTS:
                value = getattr(m, key, None)
                if value is not None:
                    constraints[key] = value
        kind = kind_of(info.annotation, info.metadata)
        if "lines" in options:
            if kind.type != "text":
                raise RecordError(f"{cls.__name__}.{name}: lines= is for vt.Text fields")
            kind = replace(kind, lines=options["lines"])
        for key in ("min_items", "max_items"):
            if key in options and kind.type != "collection":
                raise RecordError(f"{cls.__name__}.{name}: {key}= is for lists")
        out.append(FieldSpec(cls, name, kind, info.is_required(), dict(options), constraints))
    ids = [f.name for f in out if f.kind.type == "id"]
    if len(ids) > 1:
        raise RecordError(f"record {cls.__name__} has {len(ids)} vt.Id fields ({', '.join(ids)}); a record has one identity")
    _fields_cache[cls] = out
    return out


def id_field(cls: type[Record]) -> str | None:
    """The name of the record's `vt.Id` field: its identity as a document, if it has one."""
    return next((f.name for f in fields_of(cls) if f.kind.type == "id"), None)


def records_in(cls: type[Record]) -> list[type[Record]]:
    """The record and every record nested in it, through fields and collections, in first-seen order."""
    seen: list[type[Record]] = []

    def visit(r: type[Record]) -> None:
        if r in seen:
            return
        seen.append(r)
        for f in fields_of(r):
            if f.kind.record is not None:
                visit(f.kind.record)

    visit(cls)
    return seen


# `| None` means not required (05 §6.1), and so does `vt.Id`, until the app saves the record. Pydantic
# needs a default for that; it is added to the class namespace before Pydantic reads it, from the
# annotations as written, so forward references work.


def _raw_annotations(namespace: dict[str, Any]) -> dict[str, Any]:
    if "__annotations__" in namespace:
        return dict(namespace["__annotations__"])
    annotate = namespace.get("__annotate_func__") or namespace.get("__annotate__")
    if annotate is not None and sys.version_info >= (3, 14):
        import annotationlib

        return annotationlib.call_annotate_function(annotate, annotationlib.Format.STRING)
    return {}


def _allows_none(annotation: Any) -> bool:
    if isinstance(annotation, str):
        try:
            return _node_allows_none(ast.parse(annotation, mode="eval").body)
        except SyntaxError:
            return False
    if annotation is None or annotation is type(None):
        return True
    origin = get_origin(annotation)
    if origin is Annotated:
        return _allows_none(get_args(annotation)[0])
    if origin in _UNION_ORIGINS:
        return any(_allows_none(a) for a in get_args(annotation))
    return False


def _node_allows_none(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return node.value is None or (isinstance(node.value, str) and _allows_none(node.value))
    if isinstance(node, ast.Name):
        return node.id in ("None", "NoneType")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _node_allows_none(node.left) or _node_allows_none(node.right)
    if isinstance(node, ast.Subscript):
        head = node.value
        name = head.id if isinstance(head, ast.Name) else head.attr if isinstance(head, ast.Attribute) else ""
        args = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        if name == "Optional":
            return True
        if name == "Union":
            return any(_node_allows_none(a) for a in args)
        if name == "Annotated":
            return _node_allows_none(args[0])
    return False


def _is_id(annotation: Any) -> bool:
    if isinstance(annotation, str):
        try:
            node = ast.parse(annotation, mode="eval").body
        except SyntaxError:
            return False
        return (isinstance(node, ast.Name) and node.id == "Id") or (isinstance(node, ast.Attribute) and node.attr == "Id")
    return annotation is Id


def _is_classvar(annotation: Any) -> bool:
    if isinstance(annotation, str):
        return annotation.startswith(("ClassVar", "typing.ClassVar"))
    return annotation is ClassVar or get_origin(annotation) is ClassVar


def _default_optional_fields(namespace: dict[str, Any]) -> None:
    for name, annotation in _raw_annotations(namespace).items():
        if name.startswith("_") or _is_classvar(annotation):
            continue
        if not (_allows_none(annotation) or _is_id(annotation)):
            continue
        value = namespace.get(name, PydanticUndefined)
        if value is PydanticUndefined:
            namespace[name] = None
        elif isinstance(value, FieldInfo) and value.default is PydanticUndefined and value.default_factory is None:
            namespace[name] = _with_default(value, None)


def _with_default(info: FieldInfo, default: Any) -> FieldInfo:
    new = copy.copy(info)
    new.default = default
    new._attributes_set = {**info._attributes_set, "default": default}
    return new


# ── records ──────────────────────────────────────────────────────────────────


class RecordMeta(ModelMetaclass):
    """Pydantic's metaclass, plus field references on the class and `| None` meaning not required."""

    _building = 0  # while Pydantic builds a record, its `hasattr` checks on parents see no references

    def __new__(mcs, name: str, bases: tuple[type, ...], namespace: dict[str, Any], **kwargs: Any) -> type:
        _default_optional_fields(namespace)
        RecordMeta._building += 1
        try:
            cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        finally:
            RecordMeta._building -= 1
        cls.__vt_ready__ = True
        return cls

    def __getattr__(cls, name: str) -> Any:
        if not name.startswith("_") and not RecordMeta._building and "__vt_ready__" in cls.__dict__:
            if name in (cls.__dict__.get("__pydantic_fields__") or {}):
                return FieldRef(cls, name)  # type: ignore[arg-type]
        return super().__getattr__(name)  # type: ignore[misc]


class Record(BaseModel, metaclass=RecordMeta):
    """A typed record: what a frame shows or edits, and what handlers receive (05 §6.1).

    A record with a `vt.Id` field is a document the engine holds once, by that id; one without is the
    session's own. A field typed `X | None` is not required, nor is the `vt.Id` until the app saves
    the record. A record holds data: copy (`vt.t(...)`) lives in intent and is refused here.
    """

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def _no_copy(cls, value: Any) -> Any:
        if _holds_phrase(value):
            raise ValueError(
                "vt.t(...) is copy, which lives in intent: show it with vt.text(vt.t(...)) on the frame, "
                "or make the field an Enum whose members are message keys"
            )
        return value

    def update(self, other: BaseModel | dict[str, Any] | None = None, /, **values: Any) -> Record:
        """Merges fields into this record: `msg.update(saved, pending=False)`."""
        merged: dict[str, Any] = {}
        if isinstance(other, BaseModel):
            merged.update({k: getattr(other, k) for k in other.model_fields_set})
        elif other is not None:
            merged.update(other)
        merged.update(values)
        for key, value in merged.items():
            setattr(self, key, value)
        return self


def _holds_phrase(value: Any) -> bool:
    if isinstance(value, Phrase):
        return True
    if isinstance(value, (list, tuple)):
        return any(_holds_phrase(v) for v in value)
    if isinstance(value, dict):
        return any(_holds_phrase(v) for v in value.values())
    return False


def pages(ref: FieldRef) -> Any:
    """Registers a list's paging loader, after its record: `@vt.pages(Feed.posts)` (06 §5.5).

    The loader takes `ctx`, the `cursor` of the page it is asked for, and optionally the document
    that holds the list; it returns `vt.Page[Item]`. The engine fetches pages as the user nears the end.
    """
    if not isinstance(ref, FieldRef):
        raise TypeError("@vt.pages takes the list field it pages, such as @vt.pages(Feed.posts)")

    def register(loader: Any) -> Any:
        if not callable(loader):
            raise TypeError("@vt.pages decorates the loader that fetches a page")
        registered = dict(ref._record.__dict__.get("__vt_pages__", {}))
        if ref._name in registered and registered[ref._name] is not loader:
            raise ValueError(f"{ref} already has a pages loader, {name_of(registered[ref._name])}")
        registered[ref._name] = loader
        type.__setattr__(ref._record, "__vt_pages__", registered)
        return loader

    return register
