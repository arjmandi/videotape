"""Documents in the app process (05 §6.2): what a handler changes becomes `sync` ops as it is made.

The app keeps a mirror of the confirmed value of the documents its handlers touch (Q53), and each
decision works on its own tracked copy of it (Q68), so `draft.text = ""`, `conv.messages.append(msg)`,
and `msg.update(saved, pending=False)` each become an op on that document, sent in the same turn of
the event loop, tentative under that decision. Changes outside any decision (a service, or work a
handler left running) go through the mirror's own records and are confirmed at once (Q54). Paths name fields, and the items of lists of records by their key: the
item's `vt.Id`, or a key the engine (or the SDK, for an item a handler adds) gave it. Lists of
plain values change as a whole. Secret fields are never sent back. `apply_op` patches a mirrored
record with a change from the engine, without sending anything.
"""

from __future__ import annotations

import asyncio
import copy
import os
import types
from collections.abc import Callable, Iterable
from contextvars import ContextVar
from typing import Annotated, Any, Union, get_args, get_origin

from pydantic import TypeAdapter, ValidationError

from .records import Kind, Record, _tracked, explain_invalid, fields_of, id_field

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

_keys: dict[int, tuple[Any, str, bool]] = {}
"""The key of each record item the SDK tracks: id(item) → (item, key, pinned). Keys of items in the
mirror are pinned: they outlive the decision that gave them out."""

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
            entry = _keys.get(oid)
            if entry is not None and not entry[2]:
                del _keys[oid]


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


def _set_key(item: Record, key: str, pinned: bool = False) -> None:
    _keys[id(item)] = (item, key, pinned)
    scope = _scope.get()
    if scope is not None and not pinned:
        scope.append(id(item))


def known_key(item: Any) -> str | None:
    """The key an item was given, without giving it one."""
    entry = _keys.get(id(item))
    return entry[1] if entry is not None and entry[0] is item else None


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
            for item, item_data in zip(list.__iter__(value), data[spec.name]):   # raw: no copies made
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


def active() -> Tracker | None:
    """Where a change to a mirrored record goes: the decision this task runs, while it runs; else the
    app's own changes, confirmed at once (Q54)."""
    t = current.get()
    if t is not None and not t.closed:
        return t
    from . import serve

    return serve.client.outside if serve.client is not None else None


class Binding:
    """Attaches records to a document so their changes become ops: a decision's tracker, or the app's
    mirror, whose records send each change to whichever decision is running (`active`)."""

    local = False
    """Whether changes also land in the app's mirror as they are made (its records are the mirror)."""

    def target(self) -> Tracker | None:
        raise NotImplementedError

    def op(self, ref: dict[str, Any], op: dict[str, Any]) -> None:
        t = self.target()
        if t is not None:
            t.op(ref, op, self.local)

    def key(self, item: Record, key: str | None = None) -> str:
        """The item's key, given now if it has none; the mirror pins it."""
        key = key or key_of(item)
        if self.local:
            _set_key(item, key, pinned=True)
        elif known_key(item) != key:
            _set_key(item, key)
        return key

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
                    self.attach(item, ref, (*path, name, {"key": self.key(item)}))

    def _own(self, obj: Any, owner: Owner) -> None:
        _tracked[id(obj)] = (obj, owner)

    def release(self, obj: Any) -> None:
        untrack(obj)


def untrack(obj: Any) -> None:
    """Stops tracking a record and everything in it, and forgets the keys of its items."""
    if isinstance(obj, Record):
        entry = _tracked.get(id(obj))
        if entry is not None and entry[0] is obj:
            del _tracked[id(obj)]
        known = _keys.get(id(obj))
        if known is not None and known[0] is obj:
            del _keys[id(obj)]
        for spec in fields_of(type(obj)):
            child = obj.__dict__.get(spec.name)
            if isinstance(child, list):
                for item in child:
                    untrack(item)
            elif isinstance(child, Record):
                untrack(child)


class Tracker(Binding):
    """Turns changes to tracked records into ops, and hands them to `emit` once per event-loop turn.

    A tracker belongs to one decision (its ops are tentative under it) or to no decision (its ops are
    confirmed at once, as the app's own changes are). Records it adopts itself (those the mirror
    never holds: records with secrets) go to it alone.
    """

    def __init__(self, emit: Callable[[list[dict[str, Any]], str | None], None], decision: str | None = None) -> None:
        self.emit = emit
        self.decision = decision
        self.changes: list[dict[str, Any]] = []
        self.objects: list[int] = []
        self.closed = False
        self.on_local: Callable[[dict[str, Any]], None] | None = None
        """Told of each batch of changes, as it starts, that the app's mirror applied already."""
        self.copies: dict[tuple[str, str, str], Record] = {}
        """This decision's own copies of mirrored documents, by ref (Q68)."""
        self._scheduled = False
        try:
            self.loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = None

    def target(self) -> Tracker | None:
        return self

    # ── ops ──

    def op(self, ref: dict[str, Any], op: dict[str, Any], local: bool = False) -> None:  # type: ignore[override]
        if self.closed:
            return
        last = self.changes[-1] if self.changes else None
        if last is not None and last["doc"] == ref and last["local"] == local:
            last["ops"].append(op)
        else:
            self.changes.append({"doc": ref, "ops": [op], "local": local})
            if local and self.on_local is not None:
                # Counted as it is made, not when it is sent, so a sync from the engine handled
                # before the flush already knows the copy is ahead.
                self.on_local(ref)
        if not self._scheduled:
            self._scheduled = True
            if self.loop is not None and not self.loop.is_closed():
                self.loop.call_soon_threadsafe(self.flush)

    def flush(self) -> None:
        self._scheduled = False
        if not self.changes:
            return
        changes, self.changes = self.changes, []
        for change in changes:
            del change["local"]
        self.emit(changes, self.decision)

    def close(self) -> None:
        """Sends what is left and stops tracking: later changes to its own records are not sent."""
        self.flush()
        self.closed = True
        for oid in self.objects:
            _tracked.pop(oid, None)
        self.objects.clear()

    # ── attaching ──

    def working(self, src: Record, ref: dict[str, Any]) -> Record:
        """This decision's own copy of a mirrored document (Q68): the confirmed value as the mirror
        holds it, with records and lists of its own and values shared, tracked under this decision,
        and items keyed as in the mirror. One copy per document per decision."""
        key = _ref_key(ref)
        known = self.copies.get(key)
        if known is not None:
            return known
        copy = self._clone(src, ref, ())
        self.copies[key] = copy
        return copy

    def _clone(self, obj: Record, ref: dict[str, Any], path: Path) -> Record:
        cls = type(obj)
        new = object.__new__(cls)
        data = dict(obj.__dict__)
        object.__setattr__(new, "__dict__", data)
        object.__setattr__(new, "__pydantic_fields_set__", set(obj.__pydantic_fields_set__))
        object.__setattr__(new, "__pydantic_extra__", None)
        object.__setattr__(new, "__pydantic_private__", None)
        self._own(new, Owner(self, ref, path))
        for spec in fields_of(cls):
            value = data.get(spec.name)
            if value is None:
                continue
            if spec.kind.type == "record" and isinstance(value, Record):
                data[spec.name] = self._clone(value, ref, (*path, spec.name))
            elif spec.kind.type == "collection" and isinstance(value, list):
                # The list is this decision's own, but its items are the mirror's until the handler
                # reaches one, which is then copied in (copy on access): a decision that only appends
                # copies nothing.
                annotation = cls.model_fields[spec.name].annotation
                tracked = TrackedList(list.__iter__(value), self, ref, (*path, spec.name), spec.kind.item or Kind("data"), annotation)
                tracked._borrowed = {id(item) for item in list.__iter__(value) if isinstance(item, Record)}
                data[spec.name] = tracked
        return new

    def adopt(self, record: type[Record], data: Any, ref: dict[str, Any], path: Iterable[Any] = ()) -> Record:
        """A tracked record from the engine's JSON: a whole document, or an item at `path` in one."""
        path = tuple(path)
        if path and isinstance(path[-1], dict) and "key" in path[-1]:
            value = load_item(record, data, path[-1]["key"])
        else:
            value = load(record, data)
        self.attach(value, ref, path)
        return value

    def _own(self, obj: Any, owner: Owner) -> None:
        _tracked[id(obj)] = (obj, owner)
        self.objects.append(id(obj))

    def release(self, obj: Any) -> None:
        entry = _tracked.get(id(obj))
        if entry is not None and entry[0] is obj:
            del _tracked[id(obj)]


class MirrorBinding(Binding):
    """The binding of the app's mirrored records: permanent, sending each change where `active` says."""

    local = True

    def target(self) -> Tracker | None:
        return active()


MIRROR = MirrorBinding()


class Owner:
    """Where a tracked record sits: its binding, its document, and the path to it."""

    __slots__ = ("binding", "ref", "path")

    def __init__(self, binding: Binding, ref: dict[str, Any], path: Path) -> None:
        self.binding, self.ref, self.path = binding, ref, path

    def field_set(self, record: Record, name: str) -> None:
        """Called after `record.name = value` was validated and stored."""
        spec = next((s for s in fields_of(type(record)) if s.name == name), None)
        if spec is None or _secret(spec.kind):
            return
        self.binding.op(self.ref, {"op": "set", "path": _wire((*self.path, name)), "value": field_json(record, name)})
        self.binding.attach_field(record, name, self.ref, self.path)


def _ref_key(ref: dict[str, Any]) -> tuple[str, str, str]:
    return ("id", ref["record"], str(ref["id"])) if "id" in ref else ("local", ref["record"], str(ref["local"]))


def _wire(path: Path) -> list[Any]:
    return [dict(p) if isinstance(p, dict) else p for p in path]


class TrackedList(list):
    """A list in a tracked document. `append`, `prepend`, `insert`, `remove`, `pop`, and `replace`
    become ops on its items; anything else (sorting, slices, `clear`) sets the whole list."""

    def __init__(self, items: Iterable[Any], binding: Binding, ref: dict[str, Any], path: Path, item: Kind, annotation: Any) -> None:
        super().__init__(items)
        self._binding, self._ref, self._path, self._item = binding, ref, path, item
        self._adapter = TypeAdapter(_item_annotation(annotation))
        self._borrowed: set[int] = set()
        """Items that are still the mirror's (a decision's copy): copied in when the handler reaches them."""

    # ── copy on access ──

    def _at(self, index: int) -> Any:
        """The item at `index`, copied into this decision first if it is still the mirror's."""
        item = list.__getitem__(self, index)
        if self._borrowed and id(item) in self._borrowed and isinstance(self._binding, Tracker):
            self._borrowed.discard(id(item))
            key = known_key(item) or key_of(item)
            copy = self._binding._clone(item, self._ref, (*self._path, {"key": key}))
            _set_key(copy, key)
            list.__setitem__(self, index, copy)
            return copy
        return item

    def __getitem__(self, index: Any) -> Any:
        if isinstance(index, slice):
            return [self._at(i) for i in range(*index.indices(len(self)))]
        list.__getitem__(self, index)                     # raises IndexError as a list does
        return self._at(index if index >= 0 else len(self) + index)

    def __iter__(self) -> Any:
        for i in range(len(self)):
            yield self._at(i)

    def __reversed__(self) -> Any:
        for i in range(len(self) - 1, -1, -1):
            yield self._at(i)

    @property
    def _records(self) -> bool:
        return self._item.type == "record"

    def _coerce(self, value: Any) -> Any:
        if self._records and isinstance(value, self._item.target):
            return value
        try:
            return self._adapter.validate_python(value)
        except ValidationError as e:
            if self._records:
                explain_invalid(self._item.target, e)
            raise

    def _op(self, op: dict[str, Any]) -> None:
        self._binding.op(self._ref, {**op, "path": _wire(self._path)})

    def _json(self, value: Any) -> Any:
        return _item_json(value) if isinstance(value, Record) else self._adapter.dump_python(value, mode="json")

    def _whole(self) -> None:
        self._op({"op": "set", "value": [self._json(v) for v in self]})
        for item in self:
            if isinstance(item, Record):
                self._binding.attach(item, self._ref, (*self._path, {"key": self._binding.key(item)}))

    def _added(self, item: Any, at: Any) -> Any:
        if not self._records:
            self._whole()
            return item
        key = self._binding.key(item)
        self._binding.attach(item, self._ref, (*self._path, {"key": key}))
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
        at: Any = "end" if index >= size else "start" if index == 0 else {"before": key_of(list.__getitem__(self, index)) if self._records else None}
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
        self._binding.release(item)

    def remove(self, value: Any) -> None:
        index = next((i for i, v in enumerate(list.__iter__(self)) if v is value), None)
        if index is None:
            index = self.index(value)
        item = super().pop(index)
        self._removed(item)

    def pop(self, index: int = -1) -> Any:  # type: ignore[override]
        list.__getitem__(self, index)
        self._at(index if index >= 0 else len(self) + index)   # the handler gets this decision's copy
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
        index = next((i for i, v in enumerate(list.__iter__(self)) if getattr(v, ident, None) == wanted), None)
        if index is None:
            raise ValueError(f"no item has {ident}={wanted!r}")
        old = list.__getitem__(self, index)
        key = key_of(old)
        self._borrowed.discard(id(old))
        super().__setitem__(index, item)
        self._binding.release(old)
        self._binding.key(item, key)
        self._binding.attach(item, self._ref, (*self._path, {"key": key}))
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
        old = list.__getitem__(self, index)
        key = key_of(old)
        self._borrowed.discard(id(old))
        super().__setitem__(index, item)
        self._binding.release(old)
        self._binding.key(item, key)
        self._binding.attach(item, self._ref, (*self._path, {"key": key}))
        self._op({"op": "replace", "key": key, "value": dump(item)})

    def __copy__(self) -> list[Any]:
        return list(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> list[Any]:
        return [copy.deepcopy(v, memo) for v in self]

    def __reduce_ex__(self, protocol: Any) -> Any:
        return (list, (list(self),))

    def clear(self) -> None:
        for item in list.__iter__(self):
            self._binding.release(item)
        self._borrowed.clear()
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


# ── changes from the engine ──────────────────────────────────────────────────


class Unapplicable(Exception):
    """An engine change does not fit the app's copy: the copy is dropped and fetched whole again."""


def _spec(record: type[Record], name: str) -> Any:
    spec = next((s for s in fields_of(record) if s.name == name), None)
    if spec is None:
        raise Unapplicable(f"{record.__name__} has no field {name}")
    return spec


def _find(items: list[Any], key: str | None, ident: str | None) -> int:
    for i, item in enumerate(items):
        if key is not None and known_key(item) == key:
            return i
    if ident is not None:
        for i, item in enumerate(items):
            field = id_field(type(item)) if isinstance(item, Record) else None
            if field and getattr(item, field) is not None and str(getattr(item, field)) == ident:
                return i
    raise Unapplicable(f"no item {key or ident}")


def _owner(obj: Any) -> Owner:
    entry = _tracked.get(id(obj))
    if entry is None or entry[0] is not obj:
        raise Unapplicable("the copy is not tracked")
    return entry[1]


def _set_field(record: Record, name: str, value: Any) -> None:
    """Sets a field of a mirrored record from engine JSON: validated, tracked again, and not sent."""
    from pydantic import BaseModel

    spec = _spec(type(record), name)
    built: Any = value
    if value is not None and spec.kind.type == "record" and isinstance(value, dict):
        built = load(spec.kind.target, value)
    elif value is not None and spec.kind.type == "collection" and spec.kind.item is not None and spec.kind.item.type == "record":
        built = [load_item(spec.kind.item.target, v, v.get(KEY)) for v in value]
    old = record.__dict__.get(name)
    BaseModel.__setattr__(record, name, built)            # validates; skips Record's tracking hook
    if isinstance(old, (Record, list)):
        for item in old if isinstance(old, list) else [old]:
            untrack(item)
    owner = _owner(record)
    MIRROR.attach_field(record, name, owner.ref, owner.path)


def apply_op(root: Record, op: dict[str, Any]) -> None:
    """Applies one engine op to a mirrored record in place, as the engine applied it, sending nothing."""
    path = op["path"]
    if not path:
        raise Unapplicable("an empty path")
    parent: Any = root
    for seg in path[:-1]:
        if isinstance(seg, dict):
            parent = parent[_find(parent, seg.get("key"), None)] if isinstance(parent, list) else None
        else:
            parent = getattr(parent, seg, None) if isinstance(parent, Record) else None
        if parent is None:
            raise Unapplicable("the path is not in the copy")
    last = path[-1]
    kind = op["op"]
    if kind == "set":
        if isinstance(last, dict):
            if not isinstance(parent, TrackedList) or parent._item.type != "record":
                raise Unapplicable("not a list of records")
            i = _find(parent, last.get("key"), None)
            _swap(parent, i, op["value"], last["key"])
        elif isinstance(parent, Record):
            _set_field(parent, last, op["value"])
        else:
            raise Unapplicable("not a record")
        return
    if not isinstance(parent, Record) or isinstance(last, dict):
        raise Unapplicable("not a list field")
    items = getattr(parent, last, None)
    if items is None:
        _set_field(parent, last, [])
        items = getattr(parent, last)
    if not isinstance(items, TrackedList) or items._item.type != "record":
        raise Unapplicable("not a list of records")
    if kind == "remove":
        i = _find(items, op.get("key"), op.get("id"))
        untrack(list.pop(items, i))
    elif kind == "insert":
        item = load_item(items._item.target, op["value"], op["key"])
        at = op.get("at", "end")
        if at == "end":
            index = len(items)
        elif at == "start":
            index = 0
        else:
            anchor = at.get("before") or at.get("after")
            try:
                index = _find(items, anchor, None) + (0 if "before" in at else 1)
            except Unapplicable:
                index = len(items)
        list.insert(items, index, item)
        MIRROR.key(item, op["key"])
        MIRROR.attach(item, items._ref, (*items._path, {"key": op["key"]}))
    elif kind == "replace":
        i = _find(items, op.get("key"), op.get("id"))
        _swap(items, i, op["value"], known_key(items[i]) or op.get("key") or mint())
    else:
        raise Unapplicable(f"no op {kind}")


def _swap(items: TrackedList, index: int, value: Any, key: str) -> None:
    item = load_item(items._item.target, value, key)
    untrack(items[index])
    list.__setitem__(items, index, item)
    MIRROR.key(item, key)
    MIRROR.attach(item, items._ref, (*items._path, {"key": key}))
