"""What the readers find on a take, and which of it fails. Each check carries the code it fails with: VT501 an action
not found, VT502 a line misread or an option's label on a day that has none, VT503 a control the model invented,
VT504 a chart off its data, VT508 a seam between a move and its keys, and VT509 a choice not drawn marked.

The data shape, from what a reader sees to what the dailies record:

    Read      what one reader saw on one picture: its spots, every line of text with its box and whether it looks
              like a control; the boxes drawn marked; and the charts. marked and charts are None when the reader
              does not report that kind of thing, and empty when it looked and found none.
    Chart     a chart's title, its labels in order and a value per label: the screenplay's own, or what a reader saw.
    KeyChecks what every reader found on a key, judged against the key:
      actions   a Hotspot per action, found by its words by every reader, with the first reader's box        VT501
      text      a Reading per line, with a Seen per reader that read it as words                             VT502
      stray     a Sighting per reader of an option's label on a DatePicker's day with no option, or no day   VT502
      invented  a Sighting per reader of a control reading none of the key's lines, not a calendar's day     VT503
      charts    a Plotted per chart, per reader that reports charts                                          VT504
      marks     a Marked per element that offers a choice, per reader that reports marks                     VT509
    Item      one check: its code, what it is about, its evidence, whether it passed, its box, the element type it
              judges, or None for a whole-key check, and each reader's reading behind a VT501 or VT502.

A reader's spot is not always one line. A spot read across a line break is a line each, and two spots that follow
each other, side by side on a row or one under the other where a line wraps, read a line together. A DatePicker's
option label is read from the day it is drawn on, the Calendar of that reader's spots, so a label on the wrong day
is misread and one on a day with no option strays.

A reader that reports charts judges a chart whole, by VT504: its title, its labels in order, how many bars or points,
and each value within a tenth of the data. Those are facts of a chart that reading its letters cannot judge, the order
and the count and a value's size, and judging the same letters twice would fail a chart twice for one flaw, so that
reader's VT502 leaves the chart's lines out. A reader that reports no charts can only read the chart's lines as
lettering, so for it they stay in VT502."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import ClassVar, Protocol

from videotape import frames
from videotape.frames import Box, Frame
from videotape.plan import Key
from videotape.screenplay import Chart, Line, Shown

MAX_CER = 0.0
MAX_DIFFERENCE = 0.05
FIND_MAX_CER = 0.2
VALUE_TOLERANCE = 0.1
"""How far a chart's value may sit from the data, as a fraction of the data's value."""
CHOICES = ("option", "day", "tab")
"""The action kinds of lines a person chooses among, of which the one that leads to its own state is drawn marked."""


@dataclass(frozen=True)
class Spot:
    """One piece of text a reader saw, where it saw it, and whether it sat in something that looks pressable."""

    text: str
    box: Box
    control: bool


@dataclass(frozen=True)
class Read:
    """What one reader saw on one picture. marked and charts are None when the reader does not report them, and
    empty when it looked and found none."""

    reader: str
    spots: tuple[Spot, ...]
    marked: tuple[Box, ...] | None = None
    """The boxes of the spots drawn marked: lit, inverted, underlined or filled, as the chosen or current one."""
    charts: tuple[Chart, ...] | None = None


class Purse(Protocol):
    """What a paid reader asks before it sends a read, and tells after: the most the read costs is reserved, and the
    read's ledger line, or None when nothing was billed, settles it."""

    def reserve(self, usd: float) -> None: ...

    def settle(self, line: dict | None, reserved: float) -> None: ...


class Free:
    """The purse of a reader that costs nothing, which no reader asks."""

    def reserve(self, usd: float) -> None:
        pass

    def settle(self, line: dict | None, reserved: float) -> None:
        pass


class Reader(Protocol):
    """One part of an eye: it sees a key's picture and reports what it read. A reader is built for the tape it may
    cache its reads in. Its class says what it needs before it is built: the API key, or None, and whether a read
    that is not cached is a paid call."""

    name: ClassVar[str]
    key: ClassVar[str | None]
    paid: ClassVar[bool]

    def __init__(self, tape: Path) -> None: ...

    @staticmethod
    def most(width: int, height: int) -> float:
        """The most one read of a picture this size costs, which a render reserves under its cap before the read is
        sent. 0 for a reader that runs here."""
        ...

    def see(self, frame: Frame, purse: Purse = Free()) -> Read: ...


def cer(expected: str, actual: str) -> float:
    previous = list(range(len(actual) + 1))
    for i, a in enumerate(expected, 1):
        current = [i]
        for j, b in enumerate(actual, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1] / max(len(expected), 1)


def read(spots: Sequence[Spot]) -> list[str]:
    return [spot.text for spot in spots]


def find(spots: Sequence[Spot], words: str) -> Box | None:
    """The box of the spot that reads closest to the words, a control before anything else, within FIND_MAX_CER."""
    return _found("", spots, words).box


@dataclass(frozen=True)
class Seen:
    """One reader's reading of one line: what it saw, how far off, and where. Nothing seen is "" at CER 1 with no
    box."""

    reader: str
    text: str
    cer: float
    box: Box | None


@dataclass(frozen=True)
class Item:
    """One check of one take: its code, what it is about, its evidence, whether it passed, its box, the element type
    it judges, or None for a check of the whole key, and each reader's reading behind it."""

    code: str
    about: str
    result: str
    passed: bool
    box: Box | None
    element: str | None = None
    readings: tuple[Seen, ...] = ()


@dataclass(frozen=True)
class Failure:
    """A check the kept take of a shot fails."""

    code: str
    shot: str
    about: str
    """The element's label, the line, the invented control's text, the chart's title, or the seam's end."""
    evidence: str
    box: Box | None
    element: str | None = None
    readings: tuple[Seen, ...] = ()


@dataclass(frozen=True)
class Hotspot:
    """One action looked for on the key by its words: what each reader found, so the box the first reader found is
    the hotspot when every reader found it."""

    label: str
    element: str
    seen: tuple[Seen, ...]

    @property
    def box(self) -> Box | None:
        return self.seen[0].box if self.seen and all(seen.box for seen in self.seen) else None

    @property
    def missed(self) -> tuple[str, ...]:
        return tuple(seen.reader for seen in self.seen if seen.box is None)


@dataclass(frozen=True)
class Reading:
    """One line of a key, and what each reader that read it as words saw for it."""

    line: str
    element: str
    seen: tuple[Seen, ...]

    @property
    def box(self) -> Box | None:
        return next((seen.box for seen in self.seen if seen.box), None)

    @property
    def exact(self) -> bool:
        return all(seen.cer <= MAX_CER for seen in self.seen)


@dataclass(frozen=True)
class Sighting:
    """A spot one reader saw that no line accounts for."""

    reader: str
    spot: Spot


@dataclass(frozen=True)
class Plotted:
    """One chart as one reader saw it, beside the chart the screenplay plots. seen is None when the reader saw no
    chart for it."""

    reader: str
    element: str
    chart: Chart
    seen: Chart | None

    @property
    def wrong(self) -> list[str]:
        """What is off, in reading order: the title, the count or the labels, then each value past the tolerance."""
        if self.seen is None:
            return ["no chart read"]
        wrong = []
        if self.seen.title != self.chart.title:
            wrong.append(f'title read "{self.seen.title}"')
        if len(self.seen.labels) != len(self.chart.labels):
            wrong.append(f"{_counted(len(self.seen.labels), self.element)}, {len(self.chart.labels)} expected")
        elif self.seen.labels != self.chart.labels:
            wrong.append(f"labels read {', '.join(self.seen.labels)}")
        for label, value, seen in zip(self.chart.labels, self.chart.values, self.seen.values):
            if abs(seen - value) > VALUE_TOLERANCE * abs(value):
                wrong.append(f"{label} read {_number(seen)}, {_number(value)} in the data")
        return wrong


@dataclass(frozen=True)
class Marked:
    """One element that offers a choice, and which of its choices one reader saw drawn marked."""

    reader: str
    element: str
    noun: str
    """What one of its choices is called: a day, a tab or an option."""
    chosen: str | None
    marked: tuple[str, ...]
    box: Box | None
    """Where the chosen choice was read."""

    @property
    def right(self) -> bool:
        return list(self.marked) == ([self.chosen] if self.chosen else [])


def _number(value: float) -> str:
    return f"{value:,.10g}"


def _counted(number: int, element: str) -> str:
    """So many bars of a BarChart, or points of a LineChart."""
    noun = "bar" if element == "BarChart" else "point"
    return f"{number} {noun}{'' if number == 1 else 's'}"


def _placed(box: Box) -> str:
    return f"{box.x},{box.y} {box.w}x{box.h}"


def _listed(items: Sequence[str]) -> str:
    return " and ".join(filter(None, (", ".join(items[:-1]), items[-1]))) if items else "nothing"


@dataclass(frozen=True)
class KeyChecks:
    """What every reader found on a key frame, judged against the key."""

    actions: tuple[Hotspot, ...]
    text: tuple[Reading, ...]
    invented: tuple[Sighting, ...] = ()
    stray: tuple[Sighting, ...] = ()
    charts: tuple[Plotted, ...] = ()
    marks: tuple[Marked, ...] = ()

    @property
    def hotspots(self) -> dict[str, Box | None]:
        """A box per action, by its hotspot's label, or none."""
        return {hotspot.label: hotspot.box for hotspot in self.actions}

    @property
    def readers(self) -> tuple[str, ...]:
        names = [seen.reader for reading in self.text for seen in reading.seen]
        names += [seen.reader for hotspot in self.actions for seen in hotspot.seen]
        return tuple(dict.fromkeys(names))

    def items(self) -> list[Item]:
        many = len(self.readers) > 1
        items = []
        for hotspot in self.actions:
            found = hotspot.box is not None
            result = f"found at {_placed(hotspot.box)}" if found else "not found" + _by(hotspot.missed, many)
            items.append(Item("VT501", hotspot.label, result, found, hotspot.box, hotspot.element, hotspot.seen))
        for reading in self.text:
            if reading.seen:
                items.append(Item("VT502", reading.line, _read(reading.seen, many), reading.exact, reading.box,
                                  reading.element, reading.seen))
        items += [Item("VT502", sighting.spot.text, f'a day with no option shows "{sighting.spot.text}" at '
                       f"{_placed(sighting.spot.box)}{_by([sighting.reader], many)}", False, sighting.spot.box,
                       "DatePicker") for sighting in self.stray]
        items += [Item("VT503", sighting.spot.text, f'a control reading "{sighting.spot.text}" at '
                       f"{_placed(sighting.spot.box)}, and no action has those words{_by([sighting.reader], many)}",
                       False, sighting.spot.box) for sighting in self.invented]
        for plotted in self.charts:
            wrong = plotted.wrong
            result = ("; ".join(wrong) if wrong else f"{_counted(len(plotted.chart.labels), plotted.element)}, the "
                      f"title, every label and every value within {VALUE_TOLERANCE:.0%}") + _by([plotted.reader], many)
            items.append(Item("VT504", plotted.chart.title, result, not wrong, None, plotted.element))
        for mark in self.marks:
            quoted = [f'"{words}"' for words in mark.marked]
            if mark.right:
                result = f"{quoted[0]} marked, and no other {mark.noun}" if mark.chosen else f"no {mark.noun} marked"
            else:
                chosen = f'"{mark.chosen}" is chosen' if mark.chosen else f"no {mark.noun} is chosen"
                result = f"marked {_listed(quoted)}; {chosen}"
            items.append(Item("VT509", mark.chosen or mark.element, result + _by([mark.reader], many), mark.right,
                              mark.box, mark.element))
        return items

    @property
    def failures(self) -> list[Item]:
        return [item for item in self.items() if not item.passed]

    @property
    def passed(self) -> bool:
        return not self.failures

    def rank(self, seed: int) -> tuple[int, int, float, int]:
        """The most hotspots found, then the fewest invented controls, then the least character error, then the
        lowest seed."""
        found = sum(hotspot.box is not None for hotspot in self.actions)
        return -found, len(self.invented), sum(seen.cer for reading in self.text for seen in reading.seen), seed


def _by(readers: Sequence[str], many: bool) -> str:
    return f", by {_listed(list(readers))}" if many and readers else ""


def _read(seen: Sequence[Seen], many: bool) -> str:
    """The evidence of a line's VT502: what was read and how far off, by each reader when there are several."""
    texts = [f'"{one.text}"' if one.text else "nothing" for one in seen]
    if not many:
        return f"read {texts[0]}, CER {seen[0].cer:.3f}"
    return (f"read {_listed([f'{text} by {one.reader}' for text, one in zip(texts, seen)])}, CER "
            f"{_listed([f'{one.cer:.3f}' for one in seen])}")


@dataclass(frozen=True)
class MoveChecks:
    """How far a move take's first and last frames sit from the keys it is pinned to."""

    start: float
    end: float

    def items(self) -> list[Item]:
        return [Item("VT508", name, f"difference {value:.3f}", value <= MAX_DIFFERENCE, None)
                for name, value in (("start", self.start), ("end", self.end))]

    @property
    def failures(self) -> list[Item]:
        return [item for item in self.items() if not item.passed]

    @property
    def passed(self) -> bool:
        return not self.failures

    def rank(self, seed: int) -> tuple[float, int]:
        """The tightest seams at both ends, then the lowest seed."""
        return self.start + self.end, seed


Checks = KeyChecks | MoveChecks


@dataclass(frozen=True)
class _Placed:
    """One line of the key and the element it is on."""

    line: Line
    element: Shown


def score(key: Key, reads: Sequence[Read]) -> KeyChecks:
    """Judge what every reader saw against the key. Each reader finds each action by its words and reads each line,
    each from a different spot, so a line the key shows twice is read twice. A control the readings paired with a
    line is that line, misread or not; one left over that reads like no line is invented. A reader that reports
    charts judges each chart whole and leaves its lines out of its readings, and one that reports marks says which of
    an element's choices are drawn marked."""
    placed = [_Placed(line, element) for element in key.shown for line in element.lines]
    # Each option's label of a DatePicker, by its place among the key's lines, and the day it is drawn on.
    days = {index: cell[0].words for index, at in enumerate(placed) if at.element.type == "DatePicker"
            for row in at.element.rows for cell in row if len(cell) == 2 and cell[1] is at.line}
    labels = {_shape(placed[index].line.words) for index in days}
    reads = [replace(one, spots=_apart(one.spots, labels)) for one in reads]
    seen: dict[str, dict[int, Seen]] = {}
    used: dict[str, set[Spot]] = {}
    calendars: dict[str, Calendar] = {}
    for one in reads:
        judged = [index for index, at in enumerate(placed)
                  if not (one.charts is not None and at.element.chart) and index not in days]
        paired = readings(one.reader, [placed[i].line.words for i in judged], one.spots)
        seen[one.reader] = {index: found for index, (found, _) in zip(judged, paired)}
        used[one.reader] = {spot for _, spots in paired for spot in spots}
        if days:
            calendar = calendars[one.reader] = Calendar.of(one.spots, labels)
            for index, day in days.items():
                label = calendar.label(day)
                seen[one.reader][index] = (Seen(one.reader, label.text, cer(placed[index].line.words, label.text),
                                                label.box) if label else Seen(one.reader, "", 1.0, None))
                used[one.reader] |= {label} if label else set()
    text = tuple(Reading(at.line.words, at.element.type, tuple(seen[one.reader][index] for one in reads
                                                                 if index in seen[one.reader]))
                 for index, at in enumerate(placed))
    actions = tuple(Hotspot(at.line.action.label, at.element.type,
                            tuple(_found(one.reader, one.spots, at.line.action.words) for one in reads))
                    for at in placed if at.line.action)
    stray, invented = [], []
    offered = set(days.values())
    for one in reads:
        calendar = calendars.get(one.reader)
        strayed = calendar.strays(offered) if calendar else []
        stray += [Sighting(one.reader, spot) for spot in strayed]
        left = [spot for spot in one.spots if spot not in used[one.reader] and spot not in strayed]
        invented += [Sighting(one.reader, spot) for spot in left if spot.control
                     and not (calendar and spot in calendar.numbers)
                     and all(cer(line, spot.text) > FIND_MAX_CER for line in key.lines)]
    charts = [Plotted(one.reader, element.type, chart, found) for one in reads if one.charts is not None
              for element, chart, found in _plotted(key.shown, one.charts)]
    marks = [_marked(one, element, [index for index, at in enumerate(placed) if at.element is element and _choice(at.line)],
                     placed, seen[one.reader])
             for one in reads if one.marked is not None for element in key.shown
             if any(_choice(line) for line in element.lines)]
    return KeyChecks(actions, text, tuple(invented), tuple(stray), tuple(charts), tuple(marks))


def seams(first: Frame, last: Frame, start_key: Frame, end_key: Frame) -> MoveChecks:
    return MoveChecks(start=frames.difference(first, start_key), end=frames.difference(last, end_key))


def readings(reader: str, lines: Sequence[str], spots: Sequence[Spot]) -> tuple[tuple[Seen, tuple[Spot, ...]], ...]:
    """One reader's reading of each line, with the spots it was read from, each from spots no other line took, so a
    line the key shows twice is read twice. Lines read exactly by one spot are paired first, then lines read exactly
    by two spots that follow each other, the second beside the first on its row or under it where the line wraps,
    and each line left takes the closest spot still unpaired."""
    left = list(spots)
    paired: dict[int, tuple[Seen, tuple[Spot, ...]]] = {}
    for index, line in enumerate(lines):
        exact = next((spot for spot in left if spot.text == line), None)
        if exact:
            left.remove(exact)
            paired[index] = Seen(reader, line, 0.0, exact.box), (exact,)
    for index, line in enumerate(lines):
        if index not in paired:
            joined = next((pair for pair in _joins(left) if _joined(pair).text == line), None)
            if joined:
                left.remove(joined[0]), left.remove(joined[1])
                paired[index] = Seen(reader, line, 0.0, _joined(joined).box), joined
    for index, line in enumerate(lines):
        if index not in paired:
            closest = min(left, key=lambda spot: cer(line, spot.text), default=None)
            if closest is None:
                paired[index] = Seen(reader, "", 1.0, None), ()
            else:
                left.remove(closest)
                paired[index] = Seen(reader, closest.text, cer(line, closest.text), closest.box), (closest,)
    return tuple(paired[index] for index in range(len(lines)))


def _found(reader: str, spots: Sequence[Spot], words: str) -> Seen:
    """The spot that reads closest to the words, a control before anything else, within FIND_MAX_CER, or two spots
    that follow each other and read them together."""
    candidates = [*spots, *map(_joined, _joins(spots))]
    best = min(candidates, key=lambda spot: (cer(words, spot.text), not spot.control), default=None)
    if best is None or cer(words, best.text) > FIND_MAX_CER:
        return Seen(reader, "", 1.0, None)
    return Seen(reader, best.text, cer(words, best.text), best.box)


def _joins(spots: Sequence[Spot]) -> list[tuple[Spot, Spot]]:
    """Each two spots that may be one line a reader saw in two: the second just right of the first on the same row, as
    a list row's columns, or just under it and overlapping it across, as a line that wraps."""
    def under(a: Box, b: Box) -> bool:
        return a.x < b.x + b.w and b.x < a.x + a.w and 0 <= b.y - (a.y + a.h / 2) <= 1.5 * max(a.h, b.h)

    return [(a, b) for a in spots for b in spots if a is not b and (_beside(a.box, b.box) or under(a.box, b.box))]


def _beside(a: Box, b: Box) -> bool:
    """Whether b is just right of a on the same row."""
    return a.y < b.y + b.h and b.y < a.y + a.h and 0 <= b.x - (a.x + a.w) <= 1.5 * max(a.h, b.h)


def _joined(pair: tuple[Spot, Spot]) -> Spot:
    a, b = pair
    x, y = min(a.box.x, b.box.x), min(a.box.y, b.box.y)
    box = Box(x, y, max(a.box.x + a.box.w, b.box.x + b.box.w) - x, max(a.box.y + a.box.h, b.box.y + b.box.h) - y)
    return Spot(f"{a.text} {b.text}", box, a.control or b.control)


def _apart(spots: Sequence[Spot], labels: set[str]) -> tuple[Spot, ...]:
    """The spots as lines: a spot a reader read across a line break is a spot per line, each in its share of the box
    from the top, and on a calendar a day read with the label under it, as "14 $199", is the day and the label, both
    in the spot's box."""
    apart = []
    for spot in spots:
        rows = [row.strip() for row in spot.text.splitlines() if row.strip()]
        for at, row in enumerate(rows):
            box = Box(spot.box.x, spot.box.y + at * spot.box.h // len(rows), spot.box.w, spot.box.h // len(rows))
            day = re.fullmatch(r"(\d{1,2})\s+(\S.*)", row)
            if day and _day(day[1]) and _shape(day[2]) in labels:
                apart += [Spot(day[1], box, spot.control), Spot(day[2], box, spot.control)]
            else:
                apart.append(Spot(row, box, spot.control))
    return tuple(apart)


def _day(text: str) -> bool:
    return bool(re.fullmatch(r"\d{1,2}", text)) and 1 <= int(text) <= 31


@dataclass(frozen=True)
class Calendar:
    """A DatePicker as one reader saw it: each day number it read, and the label drawn on each, which is the closest
    label read under the day, within its cell, or read with it as one spot. A label on no day is left over."""

    numbers: tuple[Spot, ...]
    drawn: tuple[tuple[Spot, Spot], ...]
    """Each day with the label drawn on it, in the order the reader read the days."""
    loose: tuple[Spot, ...]

    @classmethod
    def of(cls, spots: Sequence[Spot], labels: set[str]) -> Calendar:
        numbers = tuple(spot for spot in spots if _day(spot.text))
        drawn: dict[Spot, Spot] = {}
        loose = []
        for label in (spot for spot in spots if _shape(spot.text) in labels):
            under = [day for day in numbers if day not in drawn and _on(label.box, day.box)]
            if under:
                drawn[min(under, key=lambda day: _distance(label.box, day.box))] = label
            else:
                loose.append(label)
        return cls(numbers, tuple((day, drawn[day]) for day in numbers if day in drawn), tuple(loose))

    def label(self, day: str) -> Spot | None:
        """The label drawn on the day, read first where the reader read the day more than once."""
        return next((label for number, label in self.drawn if number.text == day), None)

    def strays(self, offered: set[str]) -> list[Spot]:
        """The labels on days with no option, and those on no day at all."""
        return [label for number, label in self.drawn if number.text not in offered] + list(self.loose)


def _on(label: Box, day: Box) -> bool:
    """Whether a label sits in the day's cell: read with the day as one spot, just right of it, or under it, about
    level with it across."""
    if label == day or _beside(day, label):
        return True
    across = abs((label.x + label.w / 2) - (day.x + day.w / 2)) <= max(label.w, day.w)
    down = (label.y + label.h / 2) - (day.y + day.h / 2)
    return across and 0 < down <= 3 * max(label.h, day.h)


def _distance(label: Box, day: Box) -> float:
    return abs((label.x + label.w / 2) - (day.x + day.w / 2)) + abs((label.y + label.h / 2) - (day.y + day.h / 2))


def _shape(text: str) -> str:
    """A text's shape, which an option's label shares with another label of its kind: $219 and $1,019 are both $9."""
    return re.sub(r"[A-Za-z]+", "a", re.sub(r"[\d][\d,.]*", "9", text))


def _plotted(shown: Sequence[Shown], seen: Sequence[Chart]) -> list[tuple[Shown, Chart, Chart | None]]:
    """Each chart the key plots beside the chart a reader saw for it: the closest titles are paired first, and a
    chart left without one is paired with None."""
    plotted = [(element, element.chart) for element in shown if element.chart]
    pairs = sorted((cer(chart.title, found.title), i, j) for i, (_, chart) in enumerate(plotted)
                   for j, found in enumerate(seen))
    taken: dict[int, int] = {}
    for _, i, j in pairs:
        if i not in taken and j not in taken.values():
            taken[i] = j
    return [(element, chart, seen[taken[i]] if i in taken else None) for i, (element, chart) in enumerate(plotted)]


def _choice(line: Line) -> bool:
    return line.chosen or (line.action is not None and line.action.kind in CHOICES)


def _marked(one: Read, element: Shown, choices: Sequence[int], placed: Sequence[_Placed], seen: dict[int, Seen]) -> Marked:
    """Which of an element's choices, by their places among the key's lines, this reader saw drawn marked."""
    marked = set(one.marked or ())
    chosen = next((index for index in choices if placed[index].line.chosen), None)
    noun = next((action.kind for index in choices if (action := placed[index].line.action)), "line")
    lit = tuple(placed[index].line.words for index in choices if (found := seen.get(index)) and found.box in marked)
    box = seen[chosen].box if chosen is not None and chosen in seen else None
    return Marked(one.reader, element.type, noun, placed[chosen].line.words if chosen is not None else None, lit, box)
