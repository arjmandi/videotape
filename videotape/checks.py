"""What the readers find on a take, and which of it fails. Each check carries the code it fails with: VT501 an action
not found, VT502 a line misread or an option's label on a day that has none, VT503 a control the model invented,
VT504 a chart off its data, VT505 a variant's layout off its base's, VT506 a move that cuts, VT507 a move that
dissolves, VT508 a seam between a move and its keys, and VT509 a choice not drawn marked.

The data shape, from what a reader sees to what the dailies record:

    Read      what one reader saw on one picture: its spots, every line of text with its box and whether it looks
              like a control; the boxes drawn marked; and the charts. marked and charts are None when the reader
              does not report that kind of thing, and empty when it looked and found none.
    Chart     a chart's title, its labels in order and a value per label: the screenplay's own, or what a reader saw.
    KeyChecks what every reader found on a key, judged against the key:
      actions   a Hotspot per action, found by its words by every reader, with the first reader's box        VT501
      text      a Reading per line, with a Seen per reader that read it as words                             VT502
      stray     a Sighting per reader of a label in a DatePicker's or DateStrip's grid that is on no option   VT502
      invented  a Sighting per reader of a control reading none of the key's lines, not a calendar's day     VT503
      charts    a Plotted per chart, per reader that reports charts                                          VT504
      marks     a Marked per element that offers a choice, per reader that reports marks                     VT509
      layout    the Layout distances from the base's picture and the Bar that judges them, for a variant   VT505
    MoveChecks a move's take judged:
      start, end how far its first and last frames sit from the keys it is pinned to                       VT508
      cut       the Cut: ffmpeg's scene score of every frame, whose highest says whether the move cuts    VT506
      dissolve  the Dissolve: a judge's answer for each of FRAMES frames across the move, whether it shows
                two pictures overlaid, and what it shows                                                  VT507
    Item      one check: its code, what it is about, its evidence, whether it passed, its box, the element type it
              judges, or None for a whole-key check, and each reader's reading behind a VT501 or VT502.

A reader's spot is not always one line. A spot read across a line break is a line each, and two spots that follow
each other, both controls or neither, side by side on a row or one under the other where a line wraps, read a line
together, chosen so the most lines are read. A DatePicker's or DateStrip's option day and label are read from the
grid of its cells, the Calendar of that reader's spots, before any other line: a label on the wrong day is misread,
one on a day with no option strays, and no other line is read from the grid.

A reader that reports charts judges a chart whole, by VT504: its title, its labels in order, how many bars or points,
and each value within a tenth of the data. Those are facts of a chart that reading its letters cannot judge, the order
and the count and a value's size, and judging the same letters twice would fail a chart twice for one flaw, so that
reader's VT502 leaves the chart's lines out. A reader that reports no charts can only read the chart's lines as
lettering, so for it they stay in VT502."""

from __future__ import annotations

import math
import re
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import ClassVar, Protocol

from videotape import frames
from videotape.frames import Box, Frame
from videotape.layout import Compared
from videotape.plan import Key
from videotape.screenplay import Chart, Line, Shown

MAX_CER = 0.0
MAX_DIFFERENCE = 0.05
MAX_SCENE = 0.3
"""The scene score over which a frame is a cut. On the ten labelled moves of 2026-11-10 the three cuts score 0.319 and
up, and the seven dissolves 0.187 and under."""
FRAMES = 8
"""How many frames across a move the dissolve check judges."""
FIND_MAX_CER = 0.2
VALUE_TOLERANCE = 0.1
"""How far a chart's value may sit from the data, as a fraction of the data's value."""
CHOICES = ("option", "day", "tab")
SEARCH = 20_000
"""The most steps the search for the joins that read the most lines takes before it keeps the best it found."""
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


class Judge(Protocol):
    """What judges a move's take for the dissolve check: it is shown frames spread across the take and says of each
    whether it shows two pictures overlaid. It is built for the tape it may cache its judgments in, and its class
    says what it needs, as a Reader's does."""

    name: ClassVar[str]
    key: ClassVar[str | None]
    paid: ClassVar[bool]

    def __init__(self, tape: Path) -> None: ...

    @staticmethod
    def most(width: int, height: int) -> float:
        """The most one judgment of FRAMES frames this size costs. 0 for a judge that runs here."""
        ...

    def judge(self, sampled: Sequence[tuple[int, Frame]], purse: Purse = Free()) -> Dissolve: ...


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
    def right(self) -> bool:
        undrawn = not self.line.endswith(".") and any(seen.cer <= MAX_CER for seen in self.seen)
        return all(seen.cer <= MAX_CER or (undrawn and seen.text == f"{self.line}.") for seen in self.seen)


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
    layout: Compared | None = None

    @property
    def hotspots(self) -> dict[str, Box | None]:
        """A box per action, by its hotspot's label, or none."""
        return {hotspot.label: hotspot.box for hotspot in self.actions}

    @property
    def boxes(self) -> tuple[Box, ...]:
        """Every box a reader found on the key: each check's, and each reader's reading behind it."""
        return tuple(box for item in self.items() for box in (item.box, *(seen.box for seen in item.readings)) if box)

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
                items.append(Item("VT502", reading.line, _read(reading.seen, many), reading.right, reading.box,
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
        if self.layout is not None:
            far, bar = self.layout.layout, self.layout.bar
            items.append(Item("VT505", "layout against the base",
                              f"shading {far.shading:.4f}, edges {far.edges:.4f}, {far.kept:.0%} of the picture "
                              f"compared; {bar.metric} {'under' if self.layout.same else 'over'} the threshold of "
                              f"{bar.threshold:.4f}", self.layout.same, None))
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
class Cut:
    """ffmpeg's scene score of every frame of a move's take, how much each differs from the one before it. The
    highest after the first is the evidence: over MAX_SCENE, the move cuts there."""

    scores: tuple[float, ...]

    @property
    def top(self) -> tuple[int, float]:
        """The frame that scores highest, as ffmpeg numbers frames, from 0, and its score."""
        return max(enumerate(self.scores[1:], 1), key=lambda scored: scored[1], default=(0, 0.0))

    @property
    def passed(self) -> bool:
        return self.top[1] <= MAX_SCENE

    def item(self) -> Item:
        at, score = self.top
        return Item("VT506", f"frame {at}", f"scene score {score:.3f}, {'under' if self.passed else 'over'} the "
                    f"threshold of {MAX_SCENE}", self.passed, None)


@dataclass(frozen=True)
class Dissolve:
    """What a judge saw on frames spread across a move's take: for each, whether it shows two pictures overlaid, as
    the middle of a dissolve does, and what it shows. at numbers the frames as ffmpeg does, from 0."""

    judge: str
    at: tuple[int, ...]
    overlaid: tuple[bool, ...]
    seen: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not dissolved(self.overlaid)

    def item(self) -> Item:
        found = [str(at) for at, overlaid in zip(self.at, self.overlaid) if overlaid]
        count = len(self.overlaid)
        if found:
            about = f"frame{'s' if len(found) > 1 else ''} {_listed(found)}"
            result = f"{len(found)} of {count} frames across the move show two pictures overlaid, by {self.judge}"
        else:
            about = "no frame"
            result = f"none of {count} frames across the move shows two pictures overlaid, by {self.judge}"
        return Item("VT507", about, result, self.passed, None)


def dissolved(overlaid: Sequence[bool]) -> bool:
    """The rule: a move dissolves when any judged frame shows two pictures overlaid."""
    return any(overlaid)


@dataclass(frozen=True)
class MoveChecks:
    """A move's take judged: how far its first and last frames sit from the keys it is pinned to, and, when they were
    measured, whether it cuts and whether it dissolves."""

    start: float
    end: float
    cut: Cut | None = None
    dissolve: Dissolve | None = None

    def items(self) -> list[Item]:
        seams = [Item("VT508", name, f"difference {value:.3f}", value <= MAX_DIFFERENCE, None)
                 for name, value in (("start", self.start), ("end", self.end))]
        return [*seams, *(judged.item() for judged in (self.cut, self.dissolve) if judged is not None)]

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
    # A DatePicker's or a DateStrip's options, by their lines' places among the key's: each option's day and its
    # label, which are read from the calendar's cells before any other line is read.
    options = {index: (cell[0].words, part) for index, at in enumerate(placed) if at.element.type in DAYS
               for row in at.element.rows for cell in row if len(cell) == 2
               for part, line in (("day", cell[0]), ("label", cell[1])) if line is at.line}
    labels = {_shape(placed[index].line.words) for index, (_, part) in options.items() if part == "label"}
    kind = next((at.element.type for index, at in enumerate(placed) if index in options), "DatePicker")
    days = DAYS[kind]
    reads = [_apart(one, labels, days) for one in reads]
    if kind == "DateStrip":
        reads = [_weekdays(one) for one in reads]
    seen: dict[str, dict[int, Seen]] = {}
    sources: dict[str, dict[int, tuple[Spot, ...]]] = {}
    calendars: dict[str, Calendar] = {}
    for one in reads:
        seen[one.reader], sources[one.reader] = {}, {}
        if options:
            calendar = calendars[one.reader] = Calendar.of(one.spots, labels, days, kind == "DateStrip")
            for index, (day, part) in options.items():
                spots = calendar.days(day) if part == "day" else calendar.labels(day)
                read = " / ".join(spot.text for spot in spots)
                seen[one.reader][index] = Seen(one.reader, read, cer(placed[index].line.words, read),
                                               spots[0].box if spots else None)
                sources[one.reader][index] = spots
        taken = set(calendars[one.reader].cells) if options else set()
        judged = [index for index, at in enumerate(placed)
                  if not (one.charts is not None and at.element.chart) and index not in options]
        paired = readings(one.reader, [placed[i].line.words for i in judged],
                          [spot for spot in one.spots if spot not in taken])
        for index, (found, spots) in zip(judged, paired):
            seen[one.reader][index], sources[one.reader][index] = found, spots
    text = tuple(Reading(at.line.words, at.element.type, tuple(seen[one.reader][index] for one in reads
                                                                 if index in seen[one.reader]))
                 for index, at in enumerate(placed))
    actions = tuple(Hotspot(at.line.action.label, at.element.type,
                            tuple(_found(one.reader, one.spots, at.line.action.words) for one in reads))
                    for at in placed if at.line.action)
    stray, invented = [], []
    for one in reads:
        used = {spot for spots in sources[one.reader].values() for spot in spots}
        calendar = calendars.get(one.reader)
        strayed = calendar.strays(used) if calendar else []
        stray += [Sighting(one.reader, spot) for spot in strayed]
        left = [spot for spot in one.spots if spot not in used and spot not in strayed]
        invented += [Sighting(one.reader, spot) for spot in left if spot.control
                     and not (calendar and spot in calendar.numbers)
                     and all(cer(line, spot.text) > FIND_MAX_CER for line in key.lines)]
    charts = [Plotted(one.reader, element.type, chart, found) for one in reads if one.charts is not None
              for element, chart, found in _plotted(key.shown, one.charts)]
    marks = [_marked(one, element, [index for index, at in enumerate(placed) if at.element is element and _choice(at.line)],
                     placed, seen[one.reader], sources[one.reader],
                     calendars.get(one.reader) if element.type in DAYS else None)
             for one in reads if one.marked is not None for element in key.shown
             if any(_choice(line) for line in element.lines)]
    return KeyChecks(actions, text, tuple(invented), tuple(stray), tuple(charts), tuple(marks))


def seams(first: Frame, last: Frame, start_key: Frame, end_key: Frame) -> MoveChecks:
    return MoveChecks(start=frames.difference(first, start_key), end=frames.difference(last, end_key))


def readings(reader: str, lines: Sequence[str], spots: Sequence[Spot]) -> tuple[tuple[Seen, tuple[Spot, ...]], ...]:
    """One reader's reading of each line, with the spots it was read from, each from spots no other line took, so a
    line the key shows twice is read twice. Lines read exactly by one spot are paired first, then lines read exactly
    by two spots of the same kind that follow each other, the second beside the first on its row or under it where
    the line wraps, chosen together so that the most lines are read, and each line left takes the closest spot still
    unpaired."""
    left = list(spots)
    paired: dict[int, tuple[Seen, tuple[Spot, ...]]] = {}
    for index, line in enumerate(lines):
        exact = next((spot for spot in left if spot.text == line), None)
        if exact:
            left.remove(exact)
            paired[index] = Seen(reader, line, 0.0, exact.box), (exact,)
    joins = _joins(left)
    choices = {index: [pair for pair in joins if _joined(pair).text == line] for index, line in enumerate(lines)
               if index not in paired}
    for index, pair in _most({index: pairs for index, pairs in choices.items() if pairs}, lines).items():
        left.remove(pair[0]), left.remove(pair[1])
        paired[index] = Seen(reader, lines[index], 0.0, _joined(pair).box), pair
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
    """Each two spots that may be one line a reader saw in two: both controls or neither, the second just right of the
    first on the same row, as a list row's columns, or just under it and overlapping it across, as a line that
    wraps."""
    def under(a: Box, b: Box) -> bool:
        return a.x < b.x + b.w and b.x < a.x + a.w and 0 <= b.y - (a.y + a.h / 2) <= 1.5 * max(a.h, b.h)

    return [(a, b) for a in spots for b in spots if a is not b and a.control == b.control
            and (_beside(a.box, b.box) or under(a.box, b.box))]


def _most(choices: dict[int, list[tuple[Spot, Spot]]], lines: Sequence[str]) -> dict[int, tuple[Spot, Spot]]:
    """For each line, one of the joins that read it, so that the most lines are read and no spot is read twice. Lines
    of the same words are interchangeable, so they take their joins in one order and the first ones read, which keeps
    the search to the choices that differ. The words with the fewest joins choose first, so the first path the search
    takes is already a good one; past SEARCH steps it keeps the best found."""
    groups: dict[str, list[int]] = {}
    for index in sorted(choices):
        groups.setdefault(lines[index], []).append(index)
    order = sorted(((indexes, choices[indexes[0]]) for indexes in groups.values()), key=lambda group: len(group[1]))
    best: list[tuple[int, int]] = []
    steps = 0

    def reachable(at: int, start: int, left: int, taken: frozenset[Spot]) -> int:
        def free(pairs: list[tuple[Spot, Spot]], first: int) -> int:
            return sum(not taken & set(pair) for pair in pairs[first:])
        if at == len(order):
            return 0
        return (min(left, free(order[at][1], start)) +
                sum(min(len(indexes), free(pairs, 0)) for indexes, pairs in order[at + 1:]))

    def walk(at: int, start: int, left: int, taken: frozenset[Spot], chosen: list[tuple[int, int]]) -> None:
        nonlocal best, steps
        steps += 1
        if steps > SEARCH or len(chosen) + reachable(at, start, left, taken) <= len(best):
            return
        if at == len(order):
            best = list(chosen)
            return
        indexes, pairs = order[at]
        if left:
            for k in range(start, len(pairs)):
                if not taken & set(pairs[k]):
                    walk(at, k + 1, left - 1, taken | set(pairs[k]), [*chosen, (at, k)])
        if at + 1 < len(order):
            walk(at + 1, 0, len(order[at + 1][0]), taken, chosen)
        else:
            walk(at + 1, 0, 0, taken, chosen)

    if order:
        walk(0, 0, len(order[0][0]), frozenset(), [])
    read: dict[int, tuple[Spot, Spot]] = {}
    for at, k in best:
        indexes, pairs = order[at]
        read[next(index for index in indexes if index not in read)] = pairs[k]
    return read


def _beside(a: Box, b: Box) -> bool:
    """Whether b is just right of a on the same row."""
    return a.y < b.y + b.h and b.y < a.y + a.h and 0 <= b.x - (a.x + a.w) <= 1.5 * max(a.h, b.h)


def _joined(pair: tuple[Spot, Spot]) -> Spot:
    a, b = pair
    x, y = min(a.box.x, b.box.x), min(a.box.y, b.box.y)
    box = Box(x, y, max(a.box.x + a.box.w, b.box.x + b.box.w) - x, max(a.box.y + a.box.h, b.box.y + b.box.h) - y)
    return Spot(f"{a.text} {b.text}", box, a.control or b.control)


def _apart(one: Read, labels: set[str], days: str) -> Read:
    """The read with its spots as lines: a spot read across a line break is a spot per line, each in its share of the
    box from the top, and on a calendar a day read with the label under it, as "14 $199" or "Sat 12 $89", is the day
    and the label, both in the spot's box. A spot drawn marked is marked in every part."""
    spots, marked = [], list(one.marked or ())
    for spot in one.spots:
        rows = [row.strip() for row in spot.text.splitlines() if row.strip()]
        parts = []
        for at, row in enumerate(rows):
            box = Box(spot.box.x, spot.box.y + at * spot.box.h // len(rows), spot.box.w, spot.box.h // len(rows))
            day = re.fullmatch(rf"({days})\s+(\S.*)", row)
            if day and _shape(day[2]) in labels:
                parts += [Spot(day[1], box, spot.control), Spot(day[2], box, spot.control)]
            else:
                parts.append(Spot(row, box, spot.control))
        spots += parts
        if spot.box in marked:
            marked += [part.box for part in parts if part.box not in marked]
    return replace(one, spots=tuple(spots), marked=None if one.marked is None else tuple(marked))


def _weekdays(one: Read) -> Read:
    """The read with each weekday a reader read apart from its day, beside it or under it as a strip's tile draws
    them, read as one spot, "Fri 11", in both their boxes and marked when either is."""
    weekdays = [spot for spot in one.spots if re.fullmatch(r"[A-Z][a-z]{2}", spot.text)]
    numbers = [spot for spot in one.spots if re.fullmatch(DAYS["DatePicker"], spot.text)]
    marked = list(one.marked or ())
    joined: dict[Spot, Spot] = {}
    for weekday in weekdays:
        close = [number for number in numbers if number not in joined.values() and number.control == weekday.control
                 and (number.box == weekday.box or (weekday, number) in _joins([weekday, number]))]
        if close:
            joined[weekday] = min(close, key=lambda number: _distance(number.box, weekday.box))
    spots = []
    for spot in one.spots:
        if spot in joined:
            whole = _joined((spot, joined[spot]))
            spots.append(whole)
            if spot.box in marked or joined[spot].box in marked:
                marked.append(whole.box)
        elif spot not in joined.values():
            spots.append(spot)
    return replace(one, spots=tuple(spots), marked=None if one.marked is None else tuple(marked))


DAYS = {"DatePicker": r"(?:[1-9]|[12]\d|3[01])", "DateStrip": r"[A-Z][a-z]{2} (?:[1-9]|[12]\d|3[01])"}
"""How each element that offers days draws a day: a month's day number, or a strip's weekday and day."""


@dataclass(frozen=True)
class Calendar:
    """A DatePicker or a DateStrip as one reader saw it: the days of its grid, the label drawn on each, and the labels
    within the grid on no day. A month's grid is its lattice: the steps from a day to the next on its right and to
    the one below it, as most of its days are read, the largest group of days a step apart, and every day number on a
    point of that lattice, in its seven fullest columns and a row either side of its rows, whatever number a garbled
    cell shows. A strip's grid is its days read one after another, each its usual step from the last. So a number
    drawn between rows, past the seventh column or away from the month, or a weekday and day off the strip's line, is
    other text. A label is drawn on a day when read with it as one
    spot, just right of it, or under it within its cell, a row's step deep. No other line is read from the grid's
    days and the labels on them."""

    numbers: tuple[Spot, ...]
    drawn: tuple[tuple[Spot, Spot], ...]
    loose: tuple[Spot, ...]

    @classmethod
    def of(cls, spots: Sequence[Spot], labels: set[str], days: str, strip: bool) -> Calendar:
        found = [spot for spot in spots if re.fullmatch(days, spot.text)]
        row = None if strip else _step(found, lambda dx, dy: dy > 0 and abs(dx) < dy)
        if strip:
            grid = _strip(found)
        else:
            grid = _month(found, row)
        numbers = tuple(spot for spot in found if spot in grid or len(grid) <= 1)
        deep = max(abs(row[1]), 2 * max((spot.box.h for spot in numbers), default=0)) if row else None
        drawn: dict[Spot, Spot] = {}
        named = [spot for spot in spots if _shape(spot.text) in labels]
        for label in named:
            under = [day for day in numbers if day not in drawn and _on(label.box, day.box, deep)]
            if under:
                drawn[min(under, key=lambda day: _distance(label.box, day.box))] = label
        inside = _bounds([*(day.box for day in numbers), *(label.box for label in drawn.values())])
        loose = tuple(label for label in named if label not in drawn.values() and inside
                      and inside.x <= _cx(label.box) <= inside.x + inside.w and inside.y <= _cy(label.box) <= inside.y + inside.h)
        return cls(numbers, tuple((day, drawn[day]) for day in numbers if day in drawn), loose)

    def days(self, day: str) -> tuple[Spot, ...]:
        """Each cell of the grid that reads the day: one when the day is drawn right, and more when it is drawn
        again, which reads as all of them, so it is misread."""
        return tuple(number for number in self.numbers if number.text == day)

    def labels(self, day: str) -> tuple[Spot, ...]:
        """The labels drawn on each cell of the day, read together as its days are."""
        cells = self.days(day)
        return tuple(label for number, label in self.drawn if number in cells)

    @property
    def cells(self) -> tuple[Spot, ...]:
        """The days and the labels drawn on them, which no line but an option's is read from."""
        return (*self.numbers, *(label for _, label in self.drawn))

    def strays(self, used: set[Spot]) -> list[Spot]:
        """The grid's labels that no line was read from: on a day without an option, or within the grid on no day."""
        return [label for label in (*(label for _, label in self.drawn), *self.loose) if label not in used]


def _strip(found: Sequence[Spot]) -> list[Spot]:
    """A strip's days: the largest group read one after another, each a step from the last as most of them are, the
    step from a day to its nearest day to the right, and drawn about as tall, as a strip's cells are alike. Every day
    when no step can be read."""
    step = _step(found, lambda dx, dy: dx > 0 and abs(dy) < dx)
    if step is None:
        return list(found)

    def next_to(a: Spot, b: Spot) -> bool:
        offset = (_cx(b.box) - _cx(a.box), _cy(b.box) - _cy(a.box))
        return (min(math.dist(offset, step), math.dist(offset, (-step[0], -step[1]))) <= math.hypot(*step) / 3
                and max(a.box.h, b.box.h) <= 2 * min(a.box.h, b.box.h))

    return max(_clusters(found, next_to), key=len)


def _step(found: Sequence[Spot], toward: Callable[[float, float], bool]) -> tuple[float, float] | None:
    """The step from a day to its nearest day in one direction, as most days are read: the median of each day's."""
    steps = []
    for spot in found:
        ahead = [(_cx(other.box) - _cx(spot.box), _cy(other.box) - _cy(spot.box)) for other in found if other is not spot]
        ahead = [step for step in ahead if toward(*step)]
        if ahead:
            steps.append(min(ahead, key=lambda step: math.hypot(*step)))
    if not steps:
        return None
    return statistics.median(step[0] for step in steps), statistics.median(step[1] for step in steps)


def _month(found: Sequence[Spot], row: tuple[float, float] | None) -> list[Spot]:
    """A month's days: the largest group a column's or a row's step apart, then every day on a point of their
    lattice, in its seven fullest columns and a row either side of its rows. A sheared month leaves the nearest day
    below on either diagonal, so of the row steps a diagonal apart, the one whose lattice holds the most days is the
    row, and of those, the one most days a week apart are read across. Every day when no step can be read."""
    column = _step(found, lambda dx, dy: dx > 0 and abs(dy) < dx)
    if column is None:
        return list(found)
    steps = [step for step in (column, row) if step]

    def apart(a: Spot, b: Spot) -> bool:
        offset = (_cx(b.box) - _cx(a.box), _cy(b.box) - _cy(a.box))
        return any(math.dist(offset, step) <= math.hypot(*step) / 3 or math.dist(offset, (-step[0], -step[1]))
                   <= math.hypot(*step) / 3 for step in steps)

    linked = max(_clusters(found, apart), key=len)
    if row is None:
        return linked
    rows = (row, (row[0] + column[0], row[1] + column[1]), (row[0] - column[0], row[1] - column[1]))
    held = [(_lattice(linked, found, column, step), step) for step in rows]
    return max(held, key=lambda pair: (len(pair[0]), _weeks(linked, pair[1])))[0]


def _lattice(linked: Sequence[Spot], found: Sequence[Spot], column: tuple[float, float],
             row: tuple[float, float]) -> list[Spot]:
    """Every day on a point of the lattice the linked days lie on, in its seven fullest columns and a row either side
    of its rows, within a third of a step of a whole place."""
    determinant = column[0] * row[1] - column[1] * row[0]
    if abs(determinant) < 1e-6:
        return list(linked)
    origin = (_cx(linked[0].box), _cy(linked[0].box))

    def place(spot: Spot) -> tuple[float, float]:
        dx, dy = _cx(spot.box) - origin[0], _cy(spot.box) - origin[1]
        return (dx * row[1] - dy * row[0]) / determinant, (column[0] * dy - column[1] * dx) / determinant

    whole = [(round(u), round(v)) for u, v in map(place, linked)]
    counts = {u: sum(at == u for at, _ in whole) for u, _ in whole}
    first = max(range(min(counts), max(counts) + 1), key=lambda u: sum(counts.get(u + k, 0) for k in range(7)))
    rows = range(min(v for _, v in whole) - 1, max(v for _, v in whole) + 2)
    return [spot for spot in found if (at := place(spot)) and first <= round(at[0]) < first + 7
            and round(at[1]) in rows and abs(at[0] - round(at[0])) <= 1 / 3 and abs(at[1] - round(at[1])) <= 1 / 3]


def _weeks(days: Sequence[Spot], step: tuple[float, float]) -> int:
    """How many of the days a step apart are a week apart, across the end of a month too: the row step a calendar is
    drawn with, where a sheared month leaves the nearest day below on either diagonal."""
    def later(a: Spot, b: Spot) -> bool:
        return int(b.text) - int(a.text) in (7, -21, -22, -23, -24)

    return sum(later(a, b) for a in days for b in days
               if math.dist((_cx(b.box) - _cx(a.box), _cy(b.box) - _cy(a.box)), step) <= math.hypot(*step) / 3)


def _clusters(spots: Sequence[Spot], linked: Callable[[Spot, Spot], bool]) -> list[list[Spot]]:
    """The spots in groups, each spot with every spot it is linked to, and so on through them."""
    groups: list[list[Spot]] = []
    for spot in spots:
        near = [group for group in groups if any(linked(spot, other) for other in group)]
        groups = [group for group in groups if group not in near] + [[*(one for group in near for one in group), spot]]
    return groups


def _cx(box: Box) -> float:
    return box.x + box.w / 2


def _cy(box: Box) -> float:
    return box.y + box.h / 2


def _bounds(boxes: Sequence[Box]) -> Box | None:
    if not boxes:
        return None
    x, y = min(box.x for box in boxes), min(box.y for box in boxes)
    return Box(x, y, max(box.x + box.w for box in boxes) - x, max(box.y + box.h for box in boxes) - y)


def _on(label: Box, day: Box, deep: float | None) -> bool:
    """Whether a label sits in the day's cell: read with the day as one spot, just right of it, or under it, the
    narrower of the two centred across within the wider and its middle within the cell's depth below the day's, a
    row's step in a month or three of the taller's heights."""
    if label == day or _beside(day, label):
        return True
    narrow, wide = sorted((label, day), key=lambda box: box.w)
    across = wide.x <= narrow.x + narrow.w / 2 <= wide.x + wide.w
    down = _cy(label) - _cy(day)
    return across and 0 < down < (deep if deep is not None else 3 * max(label.h, day.h))


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


def _marked(one: Read, element: Shown, choices: Sequence[int], placed: Sequence[_Placed], seen: dict[int, Seen],
            sources: dict[int, tuple[Spot, ...]], calendar: Calendar | None) -> Marked:
    """Which of an element's choices, by their places among the key's lines, this reader saw drawn marked: those read
    from a spot drawn marked, and on a calendar any other day of its grid drawn marked too."""
    marked = set(one.marked or ())
    chosen = next((index for index in choices if placed[index].line.chosen), None)
    noun = next((action.kind for index in choices if (action := placed[index].line.action)), "line")
    lit = tuple(placed[index].line.words for index in choices
                if any(spot.box in marked for spot in sources.get(index, ())))
    read = {spot for index in choices for spot in sources.get(index, ())}
    lit += tuple(day.text for day in (calendar.numbers if calendar else ()) if day not in read and day.box in marked)
    box = seen[chosen].box if chosen is not None and chosen in seen else None
    return Marked(one.reader, element.type, noun, placed[chosen].line.words if chosen is not None else None, lit, box)
