"""An app's data: typed records, loaded from JSON files in its project into tables a scene can query."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, fields
from datetime import date, time
from operator import attrgetter
from typing import Any, ClassVar, cast, dataclass_transform, get_type_hints

from videotape import errors
from videotape.errors import ScreenplayError


@dataclass_transform(frozen_default=True)
class Record:
    """A frozen, typed record. key= names the fields that identify it."""

    __key__: ClassVar[tuple[str, ...]] = ()

    def __init_subclass__(cls, key: str | tuple[str, ...] = ()) -> None:
        dataclass(frozen=True)(cls)
        cls.__key__ = (key,) if isinstance(key, str) else tuple(key)
        _known(cls, cls.__key__)


def _names(record: type[Record]) -> list[str]:
    return [field.name for field in fields(cast(Any, record))]


def _known(record: type[Record], names: Iterable[str]) -> None:
    have = _names(record)
    for name in names:
        if name not in have:
            raise ScreenplayError("VT207", errors.here(), f'{record.__name__} has no field "{name}"',
                                  f"name one of its fields: {', '.join(have)}")


def identity(record: Record) -> tuple[object, ...]:
    """The values that identify a record: its key fields, or every field when it has no key."""
    return tuple(getattr(record, name) for name in type(record).__key__ or _names(type(record)))


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError
    return value


def _whole(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError
    return value


def _date(value: object) -> date:
    if not (isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)):
        raise ValueError
    return date.fromisoformat(value)


def _time(value: object) -> time:
    if not (isinstance(value, str) and re.fullmatch(r"\d{2}:\d{2}", value)):
        raise ValueError
    return time.fromisoformat(value)


@dataclass(frozen=True)
class _Kind:
    """One type a field can have: how an error names it, and a parse that raises ValueError on anything else."""

    says: str
    parse: Callable[[object], Any]


KINDS: dict[object, _Kind] = {
    str: _Kind("a string", _string),
    int: _Kind("a whole number", _whole),
    date: _Kind('a date like "2026-12-11"', _date),
    time: _Kind('a time like "07:05"', _time),
}


class _Mismatch(Exception):
    """What is wrong with one JSON value read as a record, said so it follows the record's name, and the fix."""

    def __init__(self, wrong: str, fix: str) -> None:
        self.wrong, self.fix = wrong, fix


def _record[R: Record](record: type[R], raw: object) -> R:
    have = _names(record)
    if not isinstance(raw, dict):
        raise _Mismatch(f"is {json.dumps(raw)}, not an object", f"write an object with the fields {', '.join(have)}")
    raw = cast(dict[str, object], raw)
    hints = get_type_hints(record)
    values: dict[str, object] = {}
    for name in have:
        kind = KINDS.get(hints[name])
        if kind is None:
            raise TypeError(f"{record.__name__}.{name} is {hints[name]!r}, and a record's field is a str, an int, "
                            "a date or a time")
        if name not in raw:
            raise _Mismatch(f'has no field "{name}"', f'add "{name}", {kind.says}')
        try:
            values[name] = kind.parse(raw[name])
        except ValueError:
            raise _Mismatch(f'field "{name}" is {json.dumps(raw[name])}, not {kind.says}',
                            f"write {kind.says}") from None
    for name in raw:
        if name not in values:
            raise _Mismatch(f'has a field "{name}" that {record.__name__} does not have',
                            f"remove it, or add {name} to {record.__name__}, whose fields are {', '.join(have)}")
    return record(**values)


@dataclass(frozen=True)
class _File:
    """A data file's text, and the path its errors show."""

    shown: str
    text: str

    def error(self, line: int, message: str, fix: str) -> ScreenplayError:
        return ScreenplayError("VT206", f"{self.shown}:{line}", message, fix)

    def line(self, number: int = 0) -> int:
        """The line the file's value starts on, or the line its array's number-th element starts on."""
        start = self._next(0)
        decoder, at = json.JSONDecoder(), start + 1
        for _ in range(number):
            start = self._next(at)
            at = decoder.raw_decode(self.text, start)[1]
        return self.text.count("\n", 0, start) + 1

    def _next(self, at: int) -> int:
        while self.text[at] in " \t\r\n,":
            at += 1
        return at


def _open(path: str) -> tuple[_File, Any]:
    asked, _ = errors.origin()
    root = next((folder for folder in asked.parents if (folder / "pyproject.toml").is_file()), None)
    if root is None:
        raise ScreenplayError("VT205", errors.here(), f'"{path}" is relative to the project, and no folder above '
                              f"{errors.shown(asked)} holds a pyproject.toml", "add a pyproject.toml to the project")
    found = root / path
    if not found.is_file():
        raise ScreenplayError("VT205", errors.here(), f"no data file at {errors.shown(found)}",
                              f'create it, or correct the path; "{path}" is relative to the folder of '
                              f"{errors.shown(root / 'pyproject.toml')}")
    file = _File(errors.shown(found), found.read_text())
    try:
        return file, json.loads(file.text)
    except json.JSONDecodeError as error:
        raise file.error(error.lineno, f"not valid JSON: {error.msg}", "correct the JSON") from None


def table[R: Record](record: type[R], path: str) -> Table[R]:
    """Load a table of records from a JSON array. The path is relative to the project."""
    file, raw = _open(path)
    if not isinstance(raw, list):
        raise file.error(file.line(), "a table's file holds an array of records, and this one does not",
                         "wrap the records in [ ], or load a single record with vt.one")
    rows, numbers = list[R](), dict[tuple[object, ...], int]()
    for number, item in enumerate(cast(list[object], raw), 1):
        try:
            row = _record(record, item)
        except _Mismatch as mismatch:
            raise file.error(file.line(number), f"record {number} {mismatch.wrong}", mismatch.fix) from None
        if record.__key__:
            key = identity(row)
            if key in numbers:
                shared = ", ".join(f"{name} {json.dumps(cast(dict[str, object], item)[name])}"
                                   for name in record.__key__)
                raise file.error(file.line(number), f"record {number} has the key of record {numbers[key]}: {shared}",
                                 f"change one of them; key= says no two records of {record.__name__} share "
                                 f"{' and '.join(record.__key__)}")
            numbers[key] = number
        rows.append(row)
    return Table(record, rows, file.shown)


def one[R: Record](record: type[R], path: str) -> R:
    """Load one record from a JSON object. The path is relative to the project."""
    file, raw = _open(path)
    try:
        return _record(record, raw)
    except _Mismatch as mismatch:
        raise file.error(file.line(), f"the record {mismatch.wrong}", mismatch.fix) from None


class Table[R: Record]:
    """Rows of one record class. A query returns a new table and leaves this one as it was."""

    def __init__(self, record: type[R], rows: Iterable[R], source: str) -> None:
        self._record, self._rows, self._source = record, tuple(rows), source

    def __iter__(self) -> Iterator[R]:
        return iter(self._rows)

    def _of(self, rows: Iterable[R]) -> Table[R]:
        return Table(self._record, rows, self._source)

    def where(self, test: Callable[[R], bool] | None = None, /, **equals: object) -> Table[R]:
        _known(self._record, equals)
        return self._of(row for row in self._rows
                        if all(getattr(row, name) == value for name, value in equals.items())
                        and (test is None or test(row)))

    def order_by(self, field: str, descending: bool = False) -> Table[R]:
        _known(self._record, [field])
        return self._of(sorted(self._rows, key=attrgetter(field), reverse=descending))

    def limit(self, n: int) -> Table[R]:
        return self._of(self._rows[:n])

    def first(self) -> R:
        if not self._rows:
            raise ScreenplayError("VT208", errors.here(),
                                  f"first() found no {self._record.__name__} from {self._source} to return",
                                  "count the rows with count() before asking for the first, or widen the query")
        return self._rows[0]

    def get(self, **equals: object) -> R:
        matches = tuple(self.where(**equals))
        if len(matches) == 1:
            return matches[0]
        asked = f"get({', '.join(f'{name}={value!r}' for name, value in equals.items())})"
        if not matches:
            raise ScreenplayError("VT208", errors.here(),
                                  f"{asked} matched no {self._record.__name__} from {self._source}",
                                  "ask for a row the data holds, or count the matches with where(...).count()")
        key = self._record.__key__
        raise ScreenplayError("VT208", errors.here(),
                              f"{asked} matched {len(matches)} rows of {self._record.__name__} from {self._source}, "
                              "and get() returns the only match",
                              (f"name the fields of its key, {' and '.join(key)}, or " if key else "")
                              + "use where(...) for several rows")

    def count(self) -> int:
        return len(self._rows)

    def distinct(self, field: str) -> list[Any]:
        _known(self._record, [field])
        return sorted({getattr(row, field) for row in self._rows})

    def min(self, field: str) -> Any:
        _known(self._record, [field])
        return min(getattr(row, field) for row in self._rows)

    def group_by[K](self, key: Callable[[R], K]) -> Groups[K, R]:
        groups: dict[K, list[R]] = {}
        for row in self._rows:
            groups.setdefault(key(row), []).append(row)
        return Groups(self._record, groups)


class Groups[K, R: Record]:
    """A table's rows, grouped by a key."""

    def __init__(self, record: type[R], groups: dict[K, list[R]]) -> None:
        self._record, self._groups = record, groups

    def count(self) -> dict[K, int]:
        return {key: len(rows) for key, rows in self._groups.items()}

    def sum(self, field: str) -> dict[K, Any]:
        _known(self._record, [field])
        return {key: sum(getattr(row, field) for row in rows) for key, rows in self._groups.items()}
