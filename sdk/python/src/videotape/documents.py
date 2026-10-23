"""Documents (05 §6.2): the engine holds each record instance once and syncs it to every screen.

`vt.docs[Conversation, cid]` is a handle on a document the engine holds, for code that runs outside
a handler, such as a service receiving a message. A handle writes: assignments and list changes
become `sync` ops, confirmed at once (tentative, when it is used inside a handler, under that
handler's decision). It does not read: the app process keeps no copy of documents, and a handler
receives the ones it needs. Changes to a document no session shows are dropped by the engine.
"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter

from .records import Record, fields_of, id_field


def _emit(ref: dict[str, Any], op: dict[str, Any]) -> None:
    from . import serve, tracking

    tracker = tracking.current.get()
    if tracker is None:
        if serve.client is None or serve.client.outside is None:
            raise RuntimeError("vt.docs needs the engine: run the app with `videotape serve`")
        tracker = serve.client.outside
    tracker.op(ref, op)


class DocHandle:
    """A document, or a nested record in one, by path; it takes changes and never reads."""

    def __init__(self, record: type[Record], ref: dict[str, Any], path: tuple[Any, ...] = ()) -> None:
        object.__setattr__(self, "_record", record)
        object.__setattr__(self, "_ref", ref)
        object.__setattr__(self, "_path", path)

    def _spec(self, name: str) -> Any:
        spec = next((s for s in fields_of(self._record) if s.name == name), None)
        if spec is None:
            raise AttributeError(f"{self._record.__name__} has no field {name!r}")
        return spec

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        spec = self._spec(name)
        if spec.kind.type == "collection":
            annotation = self._record.model_fields[name].annotation
            return ListHandle(self._record, name, annotation, self._ref, (*self._path, name))
        if spec.kind.type == "record":
            return DocHandle(spec.kind.target, self._ref, (*self._path, name))
        raise AttributeError(
            f"vt.docs[...] changes documents and does not read them; {self._record.__name__}.{name} is read in a handler"
        )

    def __setattr__(self, name: str, value: Any) -> None:
        spec = self._spec(name)
        if spec.kind.type == "secret":
            raise TypeError(f"{self._record.__name__}.{name} is a secret, which documents never hold")
        from .tracking import field_json, keys_scope

        with keys_scope():
            probe = self._record.model_construct(**{name: value})
            probe.__pydantic_validator__.validate_assignment(probe, name, value)
            _emit(self._ref, {"op": "set", "path": [*self._path, name], "value": field_json(probe, name)})

    def update(self, **values: Any) -> DocHandle:
        for key, value in values.items():
            setattr(self, key, value)
        return self


class ListHandle:
    """A list in a document: `append`, `prepend`, `remove`, and `replace` become ops on its items."""

    def __init__(self, record: type[Record], field: str, annotation: Any, ref: dict[str, Any], path: tuple[Any, ...]) -> None:
        from .tracking import _item_annotation

        self._ref, self._path = ref, path
        self._item = _item_annotation(annotation)
        self._adapter = TypeAdapter(self._item)

    def _coerce(self, value: Any) -> Any:
        if isinstance(self._item, type) and isinstance(value, self._item):
            return value
        return self._adapter.validate_python(value)

    def _insert(self, value: Any, at: str) -> Any:
        from .tracking import dump, key_of, keys_scope

        item = self._coerce(value)
        if not isinstance(item, Record):
            raise TypeError("vt.docs changes lists of records item by item; set a list of plain values whole")
        with keys_scope():
            _emit(self._ref, {"op": "insert", "path": list(self._path), "key": key_of(item), "value": dump(item), "at": at})
        return item

    def append(self, value: Any) -> Any:
        return self._insert(value, "end")

    def prepend(self, value: Any) -> Any:
        return self._insert(value, "start")

    def _id(self, item: Any) -> str:
        ident = id_field(type(item)) if isinstance(item, Record) else None
        if ident is None or getattr(item, ident) is None:
            raise TypeError("vt.docs finds list items by their vt.Id, which this item does not have")
        return str(getattr(item, ident))

    def remove(self, value: Any) -> None:
        item = self._coerce(value)
        _emit(self._ref, {"op": "remove", "path": list(self._path), "id": self._id(item)})

    def replace(self, value: Any) -> Any:
        """Replaces the item with the same `vt.Id`: `vt.docs[Pipeline, team].deals.replace(deal)`."""
        from .tracking import dump, keys_scope

        item = self._coerce(value)
        with keys_scope():
            _emit(self._ref, {"op": "replace", "path": list(self._path), "id": self._id(item), "value": dump(item)})
        return item


class _Documents:
    """`vt.docs[Conversation, cid]`: a document by record type and id, from anywhere in the app process."""

    def __getitem__(self, key: tuple[type, Any]) -> DocHandle:
        if not (isinstance(key, tuple) and len(key) == 2 and isinstance(key[0], type) and issubclass(key[0], Record)):
            raise TypeError("vt.docs takes a record type and an id: vt.docs[Conversation, conversation_id]")
        record, ident = key
        if id_field(record) is None:
            raise TypeError(f"{record.__name__} has no vt.Id, so it is a session's own document and has no address")
        return DocHandle(record, {"record": record.__name__, "id": str(ident)})


docs = _Documents()
