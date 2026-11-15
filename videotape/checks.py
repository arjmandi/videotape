"""What the eye finds on a take, and which of it fails. Each check carries the code it fails with: VT501 an action
not found, VT502 a word misread, VT503 a control the model invented, and VT508 a seam between a move and its keys."""

from dataclasses import dataclass
from typing import Protocol

from videotape import frames
from videotape.frames import Box, Frame
from videotape.plan import Key

MAX_CER = 0.0
MAX_DIFFERENCE = 0.05
FIND_MAX_CER = 0.2


@dataclass(frozen=True)
class Spot:
    """One piece of text the eye saw, where it saw it, and whether it sat in something that looks pressable."""

    text: str
    box: Box
    control: bool


class Eye(Protocol):
    name: str

    def see(self, frame: Frame) -> tuple[Spot, ...]: ...


def cer(expected: str, actual: str) -> float:
    previous = list(range(len(actual) + 1))
    for i, a in enumerate(expected, 1):
        current = [i]
        for j, b in enumerate(actual, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1] / max(len(expected), 1)


def read(seen: tuple[Spot, ...]) -> list[str]:
    return [spot.text for spot in seen]


def find(seen: tuple[Spot, ...], words: str) -> Box | None:
    """The box of the spot that reads closest to the words, a control before anything else, within FIND_MAX_CER."""
    best = min(seen, key=lambda spot: (cer(words, spot.text), not spot.control), default=None)
    return best.box if best and cer(words, best.text) <= FIND_MAX_CER else None


@dataclass(frozen=True)
class Item:
    """One check of one take: its code, what it is about, its evidence, and whether it passed."""

    code: str
    about: str
    result: str
    passed: bool
    box: Box | None


@dataclass(frozen=True)
class Failure:
    """A check the kept take of a shot fails."""

    code: str
    shot: str
    about: str
    """The element's label, the line, the invented control's text, or the seam's end."""
    evidence: str
    box: Box | None


@dataclass(frozen=True)
class Reading:
    """One line of a key, what the eye saw for it, how far apart the two are, and where it saw it."""

    line: str
    seen: str
    cer: float
    box: Box | None


def _placed(box: Box) -> str:
    return f"{box.x},{box.y} {box.w}x{box.h}"


@dataclass(frozen=True)
class KeyChecks:
    """What an eye finds on a key frame: a box per action, by its hotspot's label, or none; a reading per line; and
    every control-like box whose text is none of the key's lines."""

    hotspots: dict[str, Box | None]
    text: tuple[Reading, ...]
    invented: tuple[Spot, ...] = ()

    def items(self) -> list[Item]:
        items = [Item("VT501", label, f"found at {_placed(box)}" if box else "not found", box is not None, box)
                 for label, box in self.hotspots.items()]
        for reading in self.text:
            seen = f'"{reading.seen}"' if reading.seen else "nothing"
            items.append(Item("VT502", reading.line, f"read {seen}, CER {reading.cer:.3f}", reading.cer <= MAX_CER,
                              reading.box))
        items += [Item("VT503", spot.text, f'a control reading "{spot.text}" at {_placed(spot.box)}, and no action '
                       "has those words", False, spot.box) for spot in self.invented]
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
        found = sum(box is not None for box in self.hotspots.values())
        return -found, len(self.invented), sum(reading.cer for reading in self.text), seed


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


def score(frame: Frame, key: Key, eye: Eye) -> KeyChecks:
    """Find each of the key's actions by its words, read each of its lines, and list every control that is none of
    them. A control the readings paired with a line is that line, misread or not; one left over that reads like no
    line is invented."""
    seen = eye.see(frame)
    text = readings(key.lines, seen)
    read_as = {reading.box for reading in text if reading.box}
    return KeyChecks(
        hotspots={action.label: find(seen, action.words) for action in key.actions},
        text=text,
        invented=tuple(spot for spot in seen if spot.control and spot.box not in read_as
                       and all(cer(line, spot.text) > FIND_MAX_CER for line in key.lines)),
    )


def seams(first: Frame, last: Frame, start_key: Frame, end_key: Frame) -> MoveChecks:
    return MoveChecks(start=frames.difference(first, start_key), end=frames.difference(last, end_key))


def readings(lines: tuple[str, ...], seen: tuple[Spot, ...]) -> tuple[Reading, ...]:
    """A reading for each line, each from a different spot the eye saw, so a line the key shows twice is read twice.
    Lines seen exactly are paired first, and each line left takes the closest spot still unpaired."""
    left = list(seen)
    paired: dict[int, Reading] = {}
    for index, line in enumerate(lines):
        exact = next((spot for spot in left if spot.text == line), None)
        if exact:
            left.remove(exact)
            paired[index] = Reading(line, line, 0.0, exact.box)
    for index, line in enumerate(lines):
        if index not in paired:
            closest = min(left, key=lambda spot: cer(line, spot.text), default=None)
            if closest is None:
                paired[index] = Reading(line, "", 1.0, None)
            else:
                left.remove(closest)
                paired[index] = Reading(line, closest.text, cer(line, closest.text), closest.box)
    return tuple(paired[index] for index in range(len(lines)))
