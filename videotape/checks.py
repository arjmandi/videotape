from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from videotape import frames
from videotape.frames import Box, Frame
from videotape.screenplay import Scene

MAX_CER = 0.0
MAX_DIFFERENCE = 0.05


class ChecksError(RuntimeError):
    pass


class Eye(Protocol):
    name: str

    def find(self, frame: Frame, label: str) -> Box | None: ...

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
    seen: str
    cer: float


@dataclass(frozen=True)
class KeyChecks:
    """What an eye finds on a key frame: a box per button, or none, and a reading per line and label."""

    buttons: dict[str, Box | None]
    text: dict[str, Reading]

    def items(self) -> list[Item]:
        items = [Item(f'button "{label}"', f"found at {box.x},{box.y} {box.w}x{box.h}" if box else "not found",
                      box is not None) for label, box in self.buttons.items()]
        for text, reading in self.text.items():
            seen = f'"{reading.seen}"' if reading.seen else "nothing"
            items.append(Item(f'text "{text}"', f"read {seen}, CER {reading.cer:.3f}", reading.cer <= MAX_CER))
        return items

    @property
    def failures(self) -> list[Item]:
        return [item for item in self.items() if not item.passed]

    def rank(self, seed: int) -> tuple[int, float, int]:
        """The most buttons found, then the least character error, then the lowest seed."""
        found = sum(box is not None for box in self.buttons.values())
        return -found, sum(reading.cer for reading in self.text.values()), seed


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


def score(frame: Frame, scene: Scene, eye: Eye) -> KeyChecks:
    seen = eye.read(frame)
    return KeyChecks(
        buttons={label: eye.find(frame, label) for label in scene.actions},
        text={text: _closest(text, seen) for text in (*scene.shows, *scene.actions)},
    )


def seams(take: Path, start_key: Path, end_key: Path) -> MoveChecks:
    return MoveChecks(
        start=frames.difference(frames.first_frame(take), frames.read_png(start_key)),
        end=frames.difference(frames.last_frame(take), frames.read_png(end_key)),
    )


def _closest(text: str, seen: list[str]) -> Reading:
    return min((Reading(line, cer(text, line)) for line in seen), key=lambda reading: reading.cer, default=Reading("", 1.0))
