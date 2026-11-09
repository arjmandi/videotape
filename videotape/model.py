from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from videotape.checks import Eye
from videotape.standin import StandIn, StandInEye


class Model(Protocol):
    name: str

    def text_to_video(self, prompt: str, seed: int, out: Path) -> None: ...

    def image_to_video(self, prompt: str, start: Path, seed: int, out: Path) -> None: ...

    def first_last_frame(self, prompt: str, start: Path, end: Path, seed: int, out: Path) -> None: ...


MODELS: dict[str, Callable[[], tuple[Model, Eye]]] = {
    "stand-in": lambda: (StandIn(), StandInEye()),
}
