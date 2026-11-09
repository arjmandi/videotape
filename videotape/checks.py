from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from videotape import frames
from videotape.frames import Box, Frame
from videotape.screenplay import Scene

MAX_CER = 0.0
MAX_DIFFERENCE = 0.05


class Eye(Protocol):
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
class Checks:
    buttons: dict[str, Box | None]
    text: dict[str, float]
    start: float | None
    end: float | None

    def items(self) -> list[Item]:
        items = [Item(f'button "{label}"', f"found at {box.x},{box.y} {box.w}x{box.h}" if box else "missing",
                      box is not None) for label, box in self.buttons.items()]
        items += [Item(f'text "{text}"', f"CER {value:.3f}", value <= MAX_CER) for text, value in self.text.items()]
        for name, value in (("start", self.start), ("end", self.end)):
            if value is not None:
                items.append(Item(name, f"difference {value:.3f}", value <= MAX_DIFFERENCE))
        return items

    @property
    def failures(self) -> list[Item]:
        return [item for item in self.items() if not item.passed]


def rank(checks: Checks, seed: int) -> tuple[int, float, int]:
    return len(checks.failures), sum(checks.text.values()), seed


def check(take: Path, scene: Scene, start_key: Path | None, end_key: Path | None, eye: Eye) -> Checks:
    last = frames.last_frame(take)
    seen = eye.read(last)
    return Checks(
        buttons={label: eye.find(last, label) for label in scene.actions},
        text={text: min((cer(text, line) for line in seen), default=1.0) for text in (*scene.shows, *scene.actions)},
        start=frames.difference(frames.first_frame(take), frames.read_png(start_key)) if start_key else None,
        end=frames.difference(last, frames.read_png(end_key)) if end_key else None,
    )
