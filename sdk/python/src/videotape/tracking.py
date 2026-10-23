"""Documents in the app process (05 §6.2): what a handler changes becomes `sync` ops as it is made.

The engine sends a handler the documents its frame shows and edits; the SDK builds records from
them and tracks each one, so `draft.text = ""`, `conv.messages.append(msg)`, and
`msg.update(saved, pending=False)` each become an op on that document, sent in the same turn of
the event loop. Paths name fields, and the items of lists of records by their key: the item's
`vt.Id`, or a key the engine (or the SDK, for an item a handler adds) gave it. Lists of plain
values change as a whole. Secret fields are never sent back.
"""

from __future__ import annotations

import asyncio
import copy
import os
import types
from collections.abc import Callable, Iterable
from contextvars import ContextVar
from typing import Annotated, Any, Union, get_args, get_origin

from pydantic import TypeAdapter

from .records import Kind, Record, _tracked, fields_of, id_field

KEY = "@key"
"""Each record item of a list carries its key under this name on the wire."""

Path = tuple[Any, ...]
"""Field names, and `{"key": ...}` for an item of a list of records."""

current: ContextVar[Tracker | None] = ContextVar("videotape_tracker", default=None)
"""The tracker of the decision this task runs, so `vt.docs` inside a handler is tentative too."""

_prefix = os.urandom(3).hex()
_minted = 0


def mint() -> str:
    """A fresh key for an item a handler adds, unique across app processes."""
    global _minted
    _minted += 1
    return f"~{_prefix}.{_minted}"


# ── keys ─────────────────────────────────────────────────────────────────────

_keys: dict[int, tuple[Any, str]] = {}
"""The key of each record item the SDK tracks: id(item) → (item, key)."""

_scope: ContextVar[list[int] | None] = ContextVar("videotape_keys", default=None)


class keys_scope:
    """Forgets the keys given out inside it when it ends: one decision, one load, one `vt.docs` change."""

    def __enter__(self) -> keys_scope:
        self.ids: list[int] = []
        self.token = _scope.set(self.ids)
        return self

    def __exit__(self, *exc: Any) -> None:
        _scope.reset(self.token)
        for oid in self.ids:
            _keys.pop(oid, None)


def key_of(item: Record) -> str:
    """The item's key: the one it was given, its `vt.Id`, or a fresh one."""
    known = _keys.get(id(item))
    if known is not None and known[0] is item:
        return known[1]
    ident = id_field(type(item))
    value = getattr(item, ident) if ident else None
    key = str(value) if value is not None else mint()
    _set_key(item, key)
    return key


def _set_key(item: Record, key: str) -> None:
    _keys[id(item)] = (item, key)
    scope = _scope.get()
    if scope is not None:
        scope.append(id(item))


# ── to and from the wire ─────────────────────────────────────────────────────


def _secret(kind: Kind) -> bool:
    return kind.type == "secret"


def dump(record: Record) -> dict[str, Any]:
    """A record as the engine holds it: JSON, with the record items of its lists keyed and no secrets."""
    data = record.model_dump(mode="json")
    _annotate(record, data)
    return data


def _item_json(item: Record) -> dict[str, Any]:
    data = dump(item)
    data[KEY] = key_of(item)
    return data


def field_json(record: Record, name: str) -> Any:
    """One field's value as the engine holds it, serialised by the record's own serialiser."""
    data = record.model_dump(mode="json", include={name})
    _annotate(record, data)
    return data.get(name)


def _annotate(record: Record, data: dict[str, Any]) -> None:
    """Drops the record's secrets from `data` and keys the record items of its lists, all the way down."""
    for spec in fields_of(type(record)):
        if spec.name not in data:
            continue
        if _secret(spec.kind):
            del data[spec.name]
            continue
        value = getattr(record, spec.name)
        if spec.kind.type == "record" and isinstance(value, Record) and isinstance(data[spec.name], dict):
            _annotate(value, data[spec.name])
        elif spec.kind.type == "collection" and isinstance(value, list):
            for item, item_data in zip(value, data[spec.name]):
                if isinstance(item, Record):
                    item_data[KEY] = key_of(item)
                    _annotate(item, item_data)


def _strip(record: type[Record], data: Any) -> Any:
    """Takes the keys out of `data` (in place) and returns them as a tree that mirrors the record."""
    tree: dict[str, Any] = {}
    if not isinstance(data, dict):
        return tree
    for spec in fields_of(record):
        value = data.get(spec.name)
        target = spec.kind.record
        if value is None or target is None:
            continue
        if spec.kind.type == "record" and isinstance(value, dict):
            tree[spec.name] = _strip(target, value)
        elif spec.kind.type == "collection" and isinstance(value, list):
            keys = []
            for item in value:
                if isinstance(item, dict):
                    keys.append((item.pop(KEY, None), _strip(target, item)))
                else:
                    keys.append((None, {}))
            tree[spec.name] = keys
    return tree


def _register(record: Record, tree: dict[str, Any]) -> None:
    for name, sub in tree.items():
        value = getattr(record, name, None)
        if isinstance(sub, dict) and isinstance(value, Record):
            _register(value, sub)
        elif isinstance(sub, list) and isinstance(value, list):
            for item, (key, inner) in zip(value, sub):
                if isinstance(item, Record):
                    if key is not None:
                        _set_key(item, key)
                    _register(item, inner)


def load(record: type[Record], data: Any) -> Record:
    """A record from the engine's JSON, with the keys of its list items remembered."""
    data = copy.deepcopy(data)
    tree = _strip(record, data)
    value = record.model_validate(data)
    _register(value, tree)
    return value


def load_item(record: type[Record], data: Any, key: str | None) -> Record:
    item = load(record, data if not isinstance(data, dict) else {k: v for k, v in data.items() if k != KEY})
    if key is not None:
        _set_key(item, key)
    return item


# ── tracking ─────────────────────────────────────────────────────────────────


class Tracker:
    """Turns changes to tracked records into ops, and hands them to `emit` once per event-loop turn.

    A tracker belongs to one decision (its ops are tentative under it) or to no decision (its ops are
    confirmed at once, as `vt.docs` outside a handler makes them).
    """

    def __init__(self, emit: Callable[[list[dict[str, Any]], str | None], None], decision: str | None = None) -> None:
        self.emit = emit
        self.decision = decision
        self.changes: list[dict[str, Any]] = []
        self.objects: list[int] = []
        self.closed = False
        self._scheduled = False
        try:
            self.loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = None

    # ── ops ──

    def op(self, ref: dict[str, Any], op: dict[str, Any]) -> None:
        if self.closed:
            return
        if self.changes and self.changes[-1]["doc"] == ref:
            self.changes[-1]["ops"].append(op)
        else:
            self.changes.append({"doc": ref, "ops": [op]})
        if not self._scheduled:
            self._scheduled = True
            if self.loop is not None and not self.loop.is_closed():
                self.loop.call_soon_threadsafe(self.flush)

    def flush(self) -> None:
        self._scheduled = False
        if not self.changes:
            return
        changes, self.changes = self.changes, []
        self.emit(changes, self.decision)

    def close(self) -> None:
        """Sends what is left and stops tracking: later changes to these records are not sent."""
        self.flush()
        self.closed = True
        for oid in self.objects:
            _tracked.pop(oid, None)
        self.objects.clear()

    # ── attaching ──

    def adopt(self, record: type[Record], data: Any, ref: dict[str, Any], path: Iterable[Any] = ()) -> Record:
        """A tracked record from the engine's JSON: a whole document, or an item at `path` in one."""
        path = tuple(path)
        if path and isinstance(path[-1], dict) and "key" in path[-1]:
            value = load_item(record, data, path[-1]["key"])
        else:
            value = load(record, data)
        self.attach(value, ref, path)
        return value

    def attach(self, value: Any, ref: dict[str, Any], path: Path) -> None:
        if not isinstance(value, Record):
            return
        self._own(value, Owner(self, ref, path))
        for spec in fields_of(type(value)):
            self.attach_field(value, spec.name, ref, path)

    def attach_field(self, record: Record, name: str, ref: dict[str, Any], path: Path) -> None:
        """Tracks what a field of a tracked record holds: a nested record, or a list (wrapped)."""
        spec = next(s for s in fields_of(type(record)) if s.name == name)
        child = record.__dict__.get(name)
        if child is None:
            return
        if spec.kind.type == "record":
            self.attach(child, ref, (*path, name))
        elif spec.kind.type == "collection" and isinstance(child, list):
            annotation = type(record).model_fields[name].annotation
            tracked = TrackedList(child, self, ref, (*path, name), spec.kind.item or Kind("data"), annotation)
            record.__dict__[name] = tracked
            for item in tracked:
                if isinstance(item, Record):
                    self.attach(item, ref, (*path, name, {"key": key_of(item)}))

    def _own(self, obj: Any, owner: Owner) -> None:
        _tracked[id(obj)] = (obj, owner)
        self.objects.append(id(obj))

    def release(self, obj: Any) -> None:
        entry = _tracked.get(id(obj))
        if entry is not None and entry[0] is obj:
            del _tracked[id(obj)]


class Owner:
    """Where a tracked record sits: its document and the path to it."""

    __slots__ = ("tracker", "ref", "path")

    def __init__(self, tracker: Tracker, ref: dict[str, Any], path: Path) -> None:
        self.tracker, self.ref, self.path = tracker, ref, path

    def field_set(self, record: Record, name: str) -> None:
        """Called after `record.name = value` was validated and stored."""
        spec = next((s for s in fields_of(type(record)) if s.name == name), None)
        if spec is None or _secret(spec.kind):
            return
        self.tracker.op(self.ref, {"op": "set", "path": _wire((*self.path, name)), "value": field_json(record, name)})
        self.tracker.attach_field(record, name, self.ref, self.path)


def _wire(path: Path) -> list[Any]:
    return [dict(p) if isinstance(p, dict) else p for p in path]


class TrackedList(list):
    """A list in a tracked document. `append`, `prepend`, `insert`, `remove`, `pop`, and `replace`
    become ops on its items; anything else (sorting, slices, `clear`) sets the whole list."""

    def __init__(self, items: Iterable[Any], tracker: Tracker, ref: dict[str, Any], path: Path, item: Kind, annotation: Any) -> None:
        super().__init__(items)
        self._tracker, self._ref, self._path, self._item = tracker, ref, path, item
        self._adapter = TypeAdapter(_item_annotation(annotation))

    @property
    def _records(self) -> bool:
        return self._item.type == "record"

    def _coerce(self, value: Any) -> Any:
        if self._records and isinstance(value, self._item.target):
            return value
        return self._adapter.validate_python(value)

    def _op(self, op: dict[str, Any]) -> None:
        self._tracker.op(self._ref, {**op, "path": _wire(self._path)})

    def _json(self, value: Any) -> Any:
        return _item_json(value) if isinstance(value, Record) else self._adapter.dump_python(value, mode="json")

    def _whole(self) -> None:
        self._op({"op": "set", "value": [self._json(v) for v in self]})
        for item in self:
            if isinstance(item, Record):
                self._tracker.attach(item, self._ref, (*self._path, {"key": key_of(item)}))

    def _added(self, item: Any, at: Any) -> Any:
        if not self._records:
            self._whole()
            return item
        key = key_of(item)
        self._tracker.attach(item, self._ref, (*self._path, {"key": key}))
        self._op({"op": "insert", "key": key, "value": dump(item), "at": at})
        return item

    def append(self, value: Any) -> Any:  # type: ignore[override]
        """Adds an item at the end and returns it, so a handler can change it as the decision goes on."""
        item = self._coerce(value)
        super().append(item)
        return self._added(item, "end")

    def prepend(self, value: Any) -> Any:
        item = self._coerce(value)
        super().insert(0, item)
        return self._added(item, "start")

    def insert(self, index: int, value: Any) -> Any:  # type: ignore[override]
        item = self._coerce(value)
        size = len(self)
        if index < 0:
            index = max(0, size + index)
        at: Any = "end" if index >= size else "start" if index == 0 else {"before": key_of(self[index]) if self._records else None}
        super().insert(index, item)
        return self._added(item, at)

    def extend(self, values: Iterable[Any]) -> None:  # type: ignore[override]
        for v in values:
            self.append(v)

    def __iadd__(self, values: Iterable[Any]) -> TrackedList:  # type: ignore[override]
        self.extend(values)
        return self

    def _removed(self, item: Any) -> None:
        if not self._records:
            self._whole()
            return
        self._op({"op": "remove", "key": key_of(item)})
        self._tracker.release(item)

    def remove(self, value: Any) -> None:
        index = next((i for i, v in enumerate(self) if v is value), None)
        if index is None:
            index = self.index(value)
        item = super().pop(index)
        self._removed(item)

    def pop(self, index: int = -1) -> Any:  # type: ignore[override]
        item = super().pop(index)
        self._removed(item)
        return item

    def __delitem__(self, index: Any) -> None:
        if isinstance(index, slice):
            super().__delitem__(index)
            self._whole()
            return
        self.pop(index)

    def replace(self, value: Any) -> Any:
        """Replaces the item with the same `vt.Id` and returns the new one: `deals.replace(moved)`."""
        item = self._coerce(value)
        ident = id_field(type(item)) if self._records else None
        if ident is None:
            raise TypeError("replace() finds the item by its vt.Id, which these items do not have")
        wanted = getattr(item, ident)
        index = next((i for i, v in enumerate(self) if getattr(v, ident, None) == wanted), None)
        if index is None:
            raise ValueError(f"no item has {ident}={wanted!r}")
        old = self[index]
        key = key_of(old)
        super().__setitem__(index, item)
        self._tracker.release(old)
        _set_key(item, key)
        self._tracker.attach(item, self._ref, (*self._path, {"key": key}))
        self._op({"op": "replace", "key": key, "value": dump(item)})
        return item

    def __setitem__(self, index: Any, value: Any) -> None:
        if isinstance(index, slice):
            super().__setitem__(index, [self._coerce(v) for v in value])
            self._whole()
            return
        item = self._coerce(value)
        if not self._records:
            super().__setitem__(index, item)
            self._whole()
            return
        old = self[index]
        key = key_of(old)
        super().__setitem__(index, item)
        self._tracker.release(old)
        _set_key(item, key)
        self._tracker.attach(item, self._ref, (*self._path, {"key": key}))
        self._op({"op": "replace", "key": key, "value": dump(item)})

    def __copy__(self) -> list[Any]:
        return list(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> list[Any]:
        return [copy.deepcopy(v, memo) for v in self]

    def __reduce_ex__(self, protocol: Any) -> Any:
        return (list, (list(self),))

    def clear(self) -> None:
        for item in self:
            self._tracker.release(item)
        super().clear()
        self._whole()

    def sort(self, *args: Any, **kwargs: Any) -> None:
        super().sort(*args, **kwargs)
        self._whole()

    def reverse(self) -> None:
        super().reverse()
        self._whole()


def _item_annotation(annotation: Any) -> Any:
    """`list[Message]` → `Message`, through `| None` and `Annotated`."""
    t = annotation
    while True:
        origin = get_origin(t)
        if origin is Annotated:
            t = get_args(t)[0]
        elif origin in (Union, types.UnionType):
            args = [a for a in get_args(t) if a is not type(None)]
            t = args[0] if len(args) == 1 else Any
        else:
            break
    args = get_args(t)
    return args[0] if args else Any
