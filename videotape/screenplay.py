"""A screenplay is an app written as scenes. A scene is a function of its arguments that returns the elements it
shows, and calling it names a state for an action to lead to."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, time
from typing import NamedTuple

from videotape import errors
from videotape.data import Record, identity
from videotape.errors import ScreenplayError


@dataclass(frozen=True)
class State:
    """A scene with its arguments, and nothing else."""

    scene: Scene[...]
    args: tuple[object, ...]

    @property
    def name(self) -> str:
        return f"{self.scene.name}({', '.join(map(_named, self.args))})"


def _named(value: object) -> str:
    match value:
        case Record():
            return ", ".join(map(_named, identity(value)))
        case date():
            return value.isoformat()
        case time():
            return value.strftime("%H:%M")
        case _:
            return str(value)


class Scene[**P]:
    """A function of its arguments that returns the elements a state shows. Calling it names that state."""

    def __init__(self, build: Callable[P, Sequence[Element]]) -> None:
        self.build = build
        self.name = build.__name__
        self.defined = (build.__code__.co_filename, build.__code__.co_firstlineno)
        self.signature = inspect.signature(build)

    @property
    def called(self) -> str:
        """How a call that names one of its states is written, in a fix."""
        return f"{self.name}({'...' if self.signature.parameters else ''})"

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> State:
        bound = self.signature.bind(*args, **kwargs)
        bound.apply_defaults()
        values = tuple(bound.arguments.values())
        try:
            hash(values)
        except TypeError:
            raise TypeError(f"{self.name}'s arguments name a state, so each one is a value that can be compared, "
                            "such as a record, a date, a string or a number") from None
        return State(self, values)


class Screenplay:
    def __init__(self, title: str) -> None:
        self.title = title
        self.scenes: list[Scene[...]] = []
        self.defined = errors.here()

    def scene[**P](self, build: Callable[P, Sequence[Element]]) -> Scene[P]:
        """Make a function a scene. The first scene is the entry, where the app opens."""
        scene = Scene(build)
        self.scenes.append(scene)
        return scene


@dataclass(frozen=True)
class Action:
    """What pressing one line of a state does."""

    kind: str
    label: str
    """Its hotspot's label, which a screen reader speaks."""
    words: str
    """The line it is found by on the key."""
    to: State


@dataclass(frozen=True)
class Line:
    """One line of an element's words: what a key's prompt quotes, the checks read, and a screen reader speaks."""

    words: str
    action: Action | None = None
    chosen: bool = False


Cell = tuple[Line, ...]
"""One line, or a label beside its value."""


class Shown(NamedTuple):
    """An element on one state: its type, which a story gives an appearance and a move, and its lines. The lines are
    in rows of cells, in reading order."""

    type: str
    rows: tuple[tuple[Cell, ...], ...]

    @property
    def lines(self) -> tuple[Line, ...]:
        return tuple(line for row in self.rows for cell in row for line in cell)


def _shown(element: object, *rows: Sequence[Cell]) -> Shown:
    return Shown(type(element).__name__, tuple(tuple(row) for row in rows if row))


def _each(*lines: Line) -> list[Cell]:
    """A row in which each line is a cell of its own."""
    return [(line,) for line in lines]


def _press(on: State, kind: str, words: str, to: State | None, label: str | None = None, choice: bool = False) -> Line:
    """A line that leads to a state when pressed. Leading to the state it is on is no action, and a choice that
    does is the chosen one."""
    if to is None:
        return Line(words)
    if to == on:
        return Line(words, chosen=choice)
    return Line(words, Action(kind, label or words, words, to))


def _leads(slot: str, to: object) -> None:
    if isinstance(to, State):
        return
    if isinstance(to, Scene):
        raise ScreenplayError("VT202", errors.here(), f"{slot} is the scene {to.name} itself, not a state",
                              f"call the scene to name a state, as in {to.called}")
    raise ScreenplayError("VT202", errors.here(), f"{slot} is {to!r}, not a state",
                          "call a scene to name a state, as in to=home()")


@dataclass(frozen=True)
class Heading:
    text: str

    def show(self, on: State) -> Shown:
        return _shown(self, _each(Line(self.text)))


@dataclass(frozen=True)
class Text:
    text: str

    def show(self, on: State) -> Shown:
        return _shown(self, _each(Line(self.text)))


@dataclass(frozen=True)
class Button:
    label: str
    to: State

    def __post_init__(self) -> None:
        _leads(f'the to= of Button "{self.label}"', self.to)

    def show(self, on: State) -> Shown:
        return _shown(self, _each(_press(on, "button", self.label, self.to)))


@dataclass(frozen=True)
class Option:
    """One choice in a search bar, a date picker, or a date strip."""

    label: str
    to: State

    def __post_init__(self) -> None:
        _leads(f'the to= of Option "{self.label}"', self.to)


@dataclass(frozen=True)
class SearchBar:
    placeholder: str
    to: State | None = None
    options: Sequence[Option] = ()
    no_match: State | None = None

    def __post_init__(self) -> None:
        for name, to in (("to", self.to), ("no_match", self.no_match)):
            if to is not None:
                _leads(f'the {name}= of SearchBar "{self.placeholder}"', to)

    def show(self, on: State) -> Shown:
        bar = _press(on, "search bar", self.placeholder, self.no_match if self.options else self.to)
        options = [_press(on, "option", option.label, option.to, choice=True) for option in self.options]
        return _shown(self, _each(bar), *(_each(option) for option in options))


def _one_month(element: str, days: Mapping[date, Option]) -> None:
    months = sorted({f"{day:%B %Y}" for day in days})
    if len(months) != 1:
        raise ValueError(f"a {element}'s days are all in one month, and these are in "
                         f"{' and '.join(months) or 'none'}")


def _spoken(day: date, option: Option) -> str:
    return f"{day:%A, %B} {day.day}, {option.label}"


@dataclass(frozen=True)
class DatePicker:
    """A month calendar. days maps each day that can be picked to its option, all in one month."""

    days: Mapping[date, Option]

    def __post_init__(self) -> None:
        _one_month("DatePicker", self.days)

    def show(self, on: State) -> Shown:
        days = [(_press(on, "day", str(day.day), option.to, _spoken(day, option), choice=True), Line(option.label))
                for day, option in sorted(self.days.items())]
        return _shown(self, _each(Line(f"{min(self.days):%B %Y}")), days)


@dataclass(frozen=True)
class DateStrip:
    """A row of days. days maps each day to its option, all in one month."""

    days: Mapping[date, Option]

    def __post_init__(self) -> None:
        _one_month("DateStrip", self.days)

    def show(self, on: State) -> Shown:
        days = [(_press(on, "day", f"{day:%a} {day.day}", option.to, _spoken(day, option), choice=True),
                 Line(option.label)) for day, option in sorted(self.days.items())]
        return _shown(self, days)


@dataclass(frozen=True)
class Row:
    """One row of a list."""

    title: str
    detail: str | None = None
    value: str | None = None
    to: State | None = None

    def __post_init__(self) -> None:
        if self.to is not None:
            _leads(f'the to= of Row "{self.title}"', self.to)

    def lines(self, on: State) -> list[Line]:
        shown = [words for words in (self.title, self.detail, self.value) if words is not None]
        return [_press(on, "row", self.title, self.to, ", ".join(shown)), *map(Line, shown[1:])]


@dataclass(frozen=True)
class List:
    rows: Sequence[Row]
    title: str | None = None

    def show(self, on: State) -> Shown:
        title = [Line(self.title)] if self.title is not None else []
        return _shown(self, _each(*title), *(_each(*row.lines(on)) for row in self.rows))


def _chart(chart: BarChart | LineChart) -> Shown:
    points = [(Line(label), Line(f"{value:,}")) for label, value in chart.values.items()]
    return _shown(chart, _each(Line(chart.title)), points)


@dataclass(frozen=True)
class BarChart:
    title: str
    values: Mapping[str, float]

    def show(self, on: State) -> Shown:
        return _chart(self)


@dataclass(frozen=True)
class LineChart:
    title: str
    values: Mapping[str, float]

    def show(self, on: State) -> Shown:
        return _chart(self)


@dataclass(frozen=True)
class Tabs:
    tabs: Mapping[str, State]

    def __post_init__(self) -> None:
        for label, to in self.tabs.items():
            _leads(f'the tab "{label}"', to)

    def show(self, on: State) -> Shown:
        return _shown(self, _each(*(_press(on, "tab", label, to, choice=True) for label, to in self.tabs.items())))


Element = Heading | Text | Button | SearchBar | DatePicker | DateStrip | List | BarChart | LineChart | Tabs
