"""The app's mirror (05 §6.2, Q53, Q57): a copy of the documents its handlers touch.

The engine sends a document whole the first time a handler or loader needs it, and from then on
names it by reference and version; `sync` from the engine keeps the copy current. The copies are
live records, tracked for good, so a handler receives the copy itself and its changes go out as
ops: tentative under the decision whose task made them, or confirmed when nothing is deciding.
Those changes land in the copy as they are made, so the engine echoes them back with the version
they reached instead of sending them again. When anything does not line up (a version gap, a
change from elsewhere while the app's own are still in flight, an op that does not fit), the copy
is dropped and the engine is told (`forget`); the next request that needs it sends it whole again.
Records with secret fields are never mirrored.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .records import Record, fields_of
from .tracking import MIRROR, Unapplicable, apply_op, load, untrack


def ref_key(ref: dict[str, Any]) -> tuple[str, str, str]:
    return ("id", ref["record"], str(ref["id"])) if "id" in ref else ("local", ref["record"], str(ref["local"]))


def mirrorable(record: type[Record]) -> bool:
    """A record the app may keep a copy of: one without secret fields."""
    return not any(s.kind.type == "secret" for s in fields_of(record))


@dataclass
class Copy:
    ref: dict[str, Any]
    obj: Record
    version: int
    unacked: int = 0
    """Batches of the app's own changes the engine has not echoed yet."""


class Mirror:
    def __init__(self, record: Callable[[str], type[Record] | None], forget: Callable[[list[dict[str, Any]]], None]) -> None:
        self.record = record
        self.forget = forget
        self.copies: dict[tuple[str, str, str], Copy] = {}
        self.retired: list[Record] = []
        """Copies replaced while a handler may still hold them: released when no decision runs."""

    def __len__(self) -> int:
        return len(self.copies)

    def get(self, ref: dict[str, Any]) -> Copy | None:
        return self.copies.get(ref_key(ref))

    def adopt(self, ref: dict[str, Any], value: Any, version: int) -> Copy | None:
        """Takes a whole document from the engine as the copy of `ref` at `version`."""
        record = self.record(ref["record"])
        if record is None or not mirrorable(record) or not isinstance(value, dict):
            return None
        obj = load(record, value)
        old = self.copies.pop(ref_key(ref), None)
        if old is not None:
            self.retired.append(old.obj)
        MIRROR.attach(obj, ref, ())
        copy = Copy(ref, obj, version)
        self.copies[ref_key(ref)] = copy
        return copy

    def drop(self, ref: dict[str, Any], tell: bool = False) -> None:
        copy = self.copies.pop(ref_key(ref), None)
        if copy is None:
            return
        self.retired.append(copy.obj)
        if tell:
            self.forget([ref])

    def clear(self) -> None:
        """The connection ended: every copy goes."""
        for copy in self.copies.values():
            untrack(copy.obj)
        self.copies.clear()
        self.release_retired()

    def release_retired(self) -> None:
        for obj in self.retired:
            untrack(obj)
        self.retired.clear()

    def sent(self, ref: dict[str, Any]) -> None:
        """The app sent a batch of its own changes to this copy (it applied them already)."""
        copy = self.get(ref)
        if copy is not None:
            copy.unacked += 1

    def apply(self, change: dict[str, Any]) -> None:
        """A `sync` entry from the engine: the whole value, ops from a version, or an echo."""
        ref = change["doc"]
        if "value" in change:
            self.adopt(ref, change["value"], change["version"])
            return
        copy = self.get(ref)
        if copy is None:
            return
        if change.get("origin") == "app":
            if copy.unacked > 0 and copy.version == change.get("from"):
                copy.unacked -= 1
                copy.version = change["version"]
            else:
                self.drop(ref, tell=True)
            return
        if copy.unacked > 0 or copy.version != change.get("from"):
            self.drop(ref, tell=True)
            return
        try:
            for op in change.get("ops") or []:
                apply_op(copy.obj, op)
        except (Unapplicable, ValidationError, KeyError, TypeError, ValueError):
            self.drop(ref, tell=True)
            return
        copy.version = change["version"]
