from dataclasses import dataclass
from typing import Protocol

from videotape import frames
from videotape.frames import Box, Frame
from videotape.plan import Key

MAX_CER = 0.0
MAX_DIFFERENCE = 0.05


class ChecksError(RuntimeError):
    pass


class Eye(Protocol):
    name: str

    def find(self, frame: Frame, words: str) -> Box | None: ...

    def read(self, frame: Frame) -> list[str]: ...


def cer(expected: str, actual: str) -> float:
    previous = list(range(len(actual) + 1))
    for i, a in enumerate(expected, 1):
        current = [i]
        for j, b in enumerate(actual, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1] / max(len(expected), 1)


@dataclass(frozen=True)
class Item:
    name: str
    result: str
    passed: bool


@dataclass(frozen=True)
class Reading:
    """One line of a key, what the eye saw for it, and how far apart the two are."""

    line: str
    seen: str
    cer: float


@dataclass(frozen=True)
class KeyChecks:
    """What an eye finds on a key frame: a box per action, by its hotspot's label, or none, and a reading per line."""

    hotspots: dict[str, Box | None]
    text: tuple[Reading, ...]

    def items(self) -> list[Item]:
        items = [Item(f'hotspot "{label}"', f"found at {box.x},{box.y} {box.w}x{box.h}" if box else "not found",
                      box is not None) for label, box in self.hotspots.items()]
        for reading in self.text:
            seen = f'"{reading.seen}"' if reading.seen else "nothing"
            items.append(Item(f'text "{reading.line}"', f"read {seen}, CER {reading.cer:.3f}", reading.cer <= MAX_CER))
        return items

    @property
    def failures(self) -> list[Item]:
        return [item for item in self.items() if not item.passed]

    def rank(self, seed: int) -> tuple[int, float, int]:
        """The most hotspots found, then the least character error, then the lowest seed."""
        found = sum(box is not None for box in self.hotspots.values())
        return -found, sum(reading.cer for reading in self.text), seed


@dataclass(frozen=True)
class MoveChecks:
    """How far a move take's first and last frames sit from the keys it is pinned to."""

    start: float
    end: float

    def items(self) -> list[Item]:
        return [Item(name, f"difference {value:.3f}", value <= MAX_DIFFERENCE)
                for name, value in (("start", self.start), ("end", self.end))]

    @property
    def failures(self) -> list[Item]:
        return [item for item in self.items() if not item.passed]

    def rank(self, seed: int) -> tuple[float, int]:
        """The tightest seams at both ends, then the lowest seed."""
        return self.start + self.end, seed


Checks = KeyChecks | MoveChecks


def score(frame: Frame, key: Key, eye: Eye) -> KeyChecks:
    """Find each of the key's actions by its words, and read each of its lines."""
    return KeyChecks(
        hotspots={action.label: eye.find(frame, action.words) for action in key.actions},
        text=readings(key.lines, eye.read(frame)),
    )


def seams(first: Frame, last: Frame, start_key: Frame, end_key: Frame) -> MoveChecks:
    return MoveChecks(start=frames.difference(first, start_key), end=frames.difference(last, end_key))


def readings(lines: tuple[str, ...], seen: list[str]) -> tuple[Reading, ...]:
    """A reading for each line, each from a different line the eye saw, so a line the key shows twice is read twice.
    Lines seen exactly are paired first, and each line left takes the closest one still unpaired."""
    left = list(seen)
    paired: dict[int, Reading] = {}
    for index, line in enumerate(lines):
        if line in left:
            left.remove(line)
            paired[index] = Reading(line, line, 0.0)
    for index, line in enumerate(lines):
        if index not in paired:
            closest = min(left, key=lambda other: cer(line, other), default=None)
            if closest is None:
                paired[index] = Reading(line, "", 1.0)
            else:
                left.remove(closest)
                paired[index] = Reading(line, closest, cer(line, closest))
    return tuple(paired[index] for index in range(len(lines)))
